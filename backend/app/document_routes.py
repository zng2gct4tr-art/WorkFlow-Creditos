import os, tempfile
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from sqlalchemy import select
from .db import get_db
from .models import *
from .security import current_user, require
from .schemas import Validation
from .domain import proposal_access, serial, EDITABLE, document_ready, notify
from .audit import record

router = APIRouter(prefix="/api", tags=["Documentación"])


def document_access(db, u, did, lock=False):
    d = db.get(Document, did)
    if not d or d.deleted:
        raise HTTPException(404, "Documento no encontrado.")
    r = db.get(ProposalRequirement, d.requirement_id)
    p = proposal_access(db, u, r.proposal_id, lock)
    if u.client_id and not r.client_visible:
        raise HTTPException(404, "Documento no encontrado.")
    return d, r, p


@router.post("/requirements/{rid}/documents", status_code=201)
def upload(
    rid: str,
    request: Request,
    file: UploadFile = File(...),
    replace_id: str | None = Form(None),
    u=Depends(current_user),
    db=Depends(get_db),
):
    require(db, u, "document.upload")
    r = db.get(ProposalRequirement, rid)
    if not r:
        raise HTTPException(404, "Requisito no encontrado.")
    p = proposal_access(db, u, r.proposal_id, True)
    if u.client_id and not r.client_visible:
        raise HTTPException(404, "Requisito no encontrado.")
    old = None
    if replace_id:
        old = db.get(Document, replace_id)
        if not old or old.deleted or old.requirement_id != rid:
            raise HTTPException(
                422, "El documento a sustituir no pertenece a este requisito."
            )
    if p.state not in EDITABLE and not (
        p.state == "additional_requested" and r.additional
    ):
        raise HTTPException(409, "Los documentos están bloqueados en esta etapa.")
    settings = db.get(Setting, "files")
    config = (
        settings.value
        if settings
        else {
            "max_size_mb": 100,
            "extensions": ["pdf", "jpg", "jpeg", "png", "docx", "xlsx", "doc", "xls"],
        }
    )
    limit = int(config["max_size_mb"]) * 1024 * 1024
    filename = Path(file.filename or "").name.replace("\x00", "")[:255]
    if not filename or "/" in filename or "\\" in filename:
        raise HTTPException(422, "Nombre de archivo inválido.")
    from .documents import inspect_upload, scan_file, storage_put

    with tempfile.TemporaryDirectory(prefix="wf-upload-") as directory:
        path = Path(directory) / "upload"
        size = 0
        with path.open("wb") as target:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(
                        413,
                        "El archivo supera el límite técnico configurado por el administrador.",
                    )
                target.write(chunk)
        try:
            metadata = inspect_upload(path, filename, config["extensions"], limit)
        except ValueError as e:
            raise HTTPException(422, str(e))
        duplicate = db.scalar(
            select(Document)
            .join(ProposalRequirement)
            .where(
                ProposalRequirement.proposal_id == p.id,
                Document.sha256 == metadata["sha256"],
                Document.deleted.is_(False),
            )
        )
        if duplicate:
            raise HTTPException(409, "Este archivo ya está cargado en el expediente.")
        try:
            scan_file(path)
        except RuntimeError as e:
            raise HTTPException(503 if "no disponible" in str(e) else 422, str(e))
        key = f"{p.id}/{uid()}"
        try:
            storage_put(path, key, metadata["mime"])
        except Exception:
            raise HTTPException(
                503,
                "El almacenamiento privado no está disponible. No se guardó el documento.",
            )
    if old:
        old.deleted = True
        record(
            db,
            u,
            "document.replace",
            old.id,
            before={
                "name": old.name,
                "sha256": old.sha256,
                "storage_key": old.storage_key,
            },
            after={"replacement_key": key},
            request=request,
        )
    d = Document(
        requirement_id=rid, uploader_id=u.id, name=filename, storage_key=key, **metadata
    )
    db.add(d)
    db.flush()
    record(
        db,
        u,
        "document.upload",
        d.id,
        after={
            "requirement_id": rid,
            "name": filename,
            "sha256": d.sha256,
            "size": d.size,
            "antimalware": "passed",
        },
        request=request,
    )
    if p.state == "draft":
        from .domain import snapshot

        p.state = "documentation_pending"
        p.version += 1
        p.updated_at = now()
        snapshot(db, p, u, request, "proposal.documentation_started")
    db.commit()
    try:
        from .worker import process_document

        process_document.delay(d.id)
    except Exception:
        pass  # Durable uploaded state is picked up by the periodic outbox dispatcher.
    data = serial(d, exclude=("storage_key",))
    if u.client_id:
        data.pop("extraction", None)
        data.pop("uploader_id", None)
    return data


@router.post("/documents/{did}/validate")
def validate(
    did: str,
    body: Validation,
    request: Request,
    u=Depends(current_user),
    db=Depends(get_db),
):
    require(db, u, "document.validate")
    if u.client_id:
        raise HTTPException(403, "La validación corresponde al equipo interno.")
    d, r, p = document_access(db, u, did, True)
    if p.state in {"approved", "rejected", "cancelled"}:
        raise HTTPException(409, "La propuesta finalizada está bloqueada.")
    if d.status in {"uploaded", "processing", "processing_failed"}:
        raise HTTPException(
            409, "Espere a que termine el análisis documental antes de validar."
        )
    if body.status == "correct" and d.expires_at and d.expires_at <= now():
        raise HTTPException(
            409, "El documento está vencido. Solicite una versión vigente."
        )
    before = d.status
    d.status = body.status
    d.observations = body.reason
    db.add(
        DocumentValidation(
            document_id=did,
            actor_id=u.id,
            automatic=False,
            previous_status=before,
            status=d.status,
            reason=body.reason,
        )
    )
    record(
        db,
        u,
        "document.override",
        did,
        before={"status": before},
        after={"status": d.status, "reason": body.reason},
        request=request,
    )
    document_ready(db, p, u)
    if d.status == "incorrect":
        notify(
            db,
            p,
            "Documento rechazado",
            f"{r.name}: {body.reason}",
            client_visible=r.client_visible,
        )
    db.commit()
    return serial(d, exclude=("storage_key",))


@router.get("/documents/{did}/download-url")
def download(did: str, request: Request, u=Depends(current_user), db=Depends(get_db)):
    require(db, u, "document.download")
    d, r, p = document_access(db, u, did)
    from .documents import signed_url

    try:
        if os.getenv("STORAGE_PROVIDER", "s3") in {"azure", "local"}:
            from .download_tokens import token_for

            url = f"/api/documents/{d.id}/content?token=" + token_for(
                d.id, u.id, request.state.session_id
            )
        else:
            url = signed_url(d.storage_key, d.name)
    except Exception:
        raise HTTPException(503, "No se pudo generar el acceso temporal al documento.")
    record(
        db,
        u,
        "document.download",
        d.id,
        after={"expires_in": 120, "sha256": d.sha256},
        request=request,
    )
    db.commit()
    return {"url": url, "expires_in": 120}


@router.get("/documents/{did}")
def view(did: str, request: Request, u=Depends(current_user), db=Depends(get_db)):
    require(db, u, "document.download")
    d, r, p = document_access(db, u, did)
    record(db, u, "document.view", d.id, request=request)
    db.commit()
    data = serial(d, exclude=("storage_key",))
    if u.client_id:
        data.pop("extraction", None)
        data.pop("uploader_id", None)
    return data


@router.delete("/documents/{did}")
def remove(did: str, request: Request, u=Depends(current_user), db=Depends(get_db)):
    require(db, u, "document.upload")
    d, r, p = document_access(db, u, did, True)
    if p.state not in EDITABLE and not (
        p.state == "additional_requested" and r.additional
    ):
        raise HTTPException(409, "Los documentos están bloqueados en esta etapa.")
    d.deleted = True
    record(
        db,
        u,
        "document.delete",
        did,
        after={"sha256": d.sha256, "logical": True},
        request=request,
    )
    db.commit()
    return {"message": "Documento retirado del checklist. La acción queda auditada."}


@router.get("/documents/{did}/content")
def content(
    did: str, token: str, request: Request, u=Depends(current_user), db=Depends(get_db)
):
    require(db, u, "document.download")
    d, r, p = document_access(db, u, did)
    from .download_tokens import verify_token

    verify_token(token, did, u.id, request.state.session_id)
    from .documents import storage_get
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask
    import shutil, hashlib

    directory = tempfile.mkdtemp(prefix="wf-download-")
    path = Path(directory) / "document"
    try:
        storage_get(d.storage_key, path)
        with path.open("rb") as source:
            checksum = hashlib.file_digest(source, "sha256").hexdigest()
        if checksum != d.sha256:
            raise RuntimeError("integrity check failed")
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        record(db, u, "document.integrity_or_storage_failed", d.id, request=request)
        db.commit()
        raise HTTPException(
            503,
            "No se pudo recuperar el documento de forma segura. Contacte al administrador.",
        )
    record(
        db,
        u,
        "document.content_access",
        d.id,
        after={"sha256": d.sha256},
        request=request,
    )
    db.commit()
    return FileResponse(
        path,
        media_type=d.mime,
        filename=d.name,
        background=BackgroundTask(shutil.rmtree, directory, ignore_errors=True),
    )
