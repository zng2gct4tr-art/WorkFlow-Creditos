from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, text
from .db import get_db
from .models import *
from .security import current_user, require, permissions
from .schemas import (
    ProposalInput,
    ProposalPatch,
    Transition,
    Assignment,
    ReportInput,
    CommentInput,
)
from .domain import *
from .audit import record

router = APIRouter(prefix="/api/proposals", tags=["Propuestas"])


@router.get("")
def list_proposals(
    state: str = "",
    client_id: str = "",
    product_id: str = "",
    currency: str = "",
    manager_id: str = "",
    analyst_id: str = "",
    branch: str = "",
    activity: str = "",
    profile_id: str = "",
    amount_min: float | None = None,
    amount_max: float | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sla: str = "",
    u=Depends(current_user),
    db=Depends(get_db),
):
    q = scoped_proposals(db, u).join(Client)
    if state:
        q = q.where(Proposal.state == state)
    if client_id:
        q = q.where(Proposal.client_id == client_id)
    if product_id:
        q = q.where(Proposal.product_id == product_id)
    if currency:
        q = q.where(Proposal.currency == currency)
    if manager_id:
        q = q.where(Client.manager_id == manager_id)
    if analyst_id:
        q = q.where(
            Proposal.id.in_(
                select(AnalystAssignment.proposal_id).where(
                    AnalystAssignment.user_id == analyst_id,
                    AnalystAssignment.active.is_(True),
                )
            )
        )
    if branch:
        q = q.where(Client.branch == branch)
    if activity:
        q = q.where(Client.activity.ilike("%" + activity[:200] + "%"))
    if profile_id:
        q = q.where(Client.profile_id == profile_id)
    if amount_min is not None:
        q = q.where(Proposal.amount >= amount_min)
    if amount_max is not None:
        q = q.where(Proposal.amount <= amount_max)
    if date_from:
        q = q.where(Proposal.created_at >= date_from)
    if date_to:
        q = q.where(Proposal.created_at <= date_to)
    data = [
        proposal_dict(db, p, u)
        for p in db.scalars(q.order_by(Proposal.created_at.desc()).limit(500))
    ]
    if sla:
        data = [p for p in data if any(s["color"] == sla for s in p["sla"].values())]
    return data


@router.post("", status_code=201)
def create(
    body: ProposalInput, request: Request, u=Depends(current_user), db=Depends(get_db)
):
    require(db, u, "proposal.create")
    c = client_access(
        db,
        u,
        db.scalar(select(Client).where(Client.id == body.client_id).with_for_update()),
    )
    if u.client_id or (
        c.manager_id != u.id and "portfolio.all" not in permissions(db, u)
    ):
        raise HTTPException(403, "Solo puede crear propuestas para su cartera.")
    if db.scalar(
        select(Proposal).where(
            Proposal.client_id == c.id, Proposal.state.not_in(TERMINAL)
        )
    ):
        raise HTTPException(409, "La empresa ya tiene una propuesta activa.")
    product = db.get(Product, body.product_id)
    if not product or not product.active:
        raise HTTPException(422, "Seleccione un producto activo.")
    number = db.scalar(text("SELECT nextval('credit_proposal_number')"))
    p = Proposal(
        **body.model_dump(),
        code=f"CR-{now().astimezone(__import__('zoneinfo').ZoneInfo('America/Montevideo')).year}-{number:06d}",
    )
    db.add(p)
    db.flush()
    # Snapshot template rules, so administrative changes cannot retroactively alter this case.
    templates = list(
        db.scalars(
            select(ChecklistRequirement).where(
                ChecklistRequirement.profile_id == c.profile_id,
                ChecklistRequirement.active.is_(True),
            )
        )
    )
    required = 0
    for t in templates:
        conditions = t.conditions or {}
        if conditions.get("min_amount") is not None and p.amount < __import__(
            "decimal"
        ).Decimal(str(conditions["min_amount"])):
            continue
        if conditions.get("max_amount") is not None and p.amount > __import__(
            "decimal"
        ).Decimal(str(conditions["max_amount"])):
            continue
        if conditions.get("products") and p.product_id not in conditions["products"]:
            continue
        if conditions.get("activities") and c.activity not in conditions["activities"]:
            continue
        db.add(
            ProposalRequirement(
                proposal_id=p.id,
                template_id=t.id,
                name=t.name,
                category=t.category,
                mandatory=t.mandatory,
                rules=t.rules,
                validity_days=t.validity_days,
            )
        )
        required += int(t.mandatory)
    if not required:
        raise HTTPException(
            409,
            "El perfil no tiene requisitos obligatorios aplicables. Configure el checklist antes de crear propuestas.",
        )
    snapshot(db, p, u, request, "proposal.create")
    db.commit()
    return proposal_dict(db, p, u)


@router.get("/{pid}")
def detail(pid: str, request: Request, u=Depends(current_user), db=Depends(get_db)):
    p = proposal_access(db, u, pid)
    record(db, u, "proposal.view", pid, request=request)
    db.commit()
    return proposal_dict(db, p, u)


@router.patch("/{pid}")
def patch(
    pid: str,
    body: ProposalPatch,
    request: Request,
    u=Depends(current_user),
    db=Depends(get_db),
):
    require(db, u, "proposal.edit")
    p = proposal_access(db, u, pid, True)
    check_manager(db, u, p)
    if p.state not in EDITABLE:
        raise HTTPException(409, "La propuesta enviada a análisis está bloqueada.")
    if p.version != body.version:
        raise HTTPException(409, "La propuesta cambió. Actualice antes de guardar.")
    before = serial(p)
    for k, v in body.model_dump(exclude_unset=True).items():
        if k != "version":
            if v is None:
                raise HTTPException(
                    422, "No se admiten valores vacíos para estos campos."
                )
            setattr(p, k, v)
    p.version += 1
    p.updated_at = now()
    snapshot(db, p, u, request)
    record(
        db, u, "proposal.change", pid, before=before, after=serial(p), request=request
    )
    db.commit()
    return proposal_dict(db, p, u)


@router.post("/{pid}/transition")
def change_state(
    pid: str,
    body: Transition,
    request: Request,
    u=Depends(current_user),
    db=Depends(get_db),
):
    p = proposal_access(db, u, pid, True)
    transition(db, u, p, body, request)
    db.commit()
    return proposal_dict(db, p, u)


@router.get("/{pid}/versions")
def versions(pid: str, u=Depends(current_user), db=Depends(get_db)):
    p = proposal_access(db, u, pid)
    if u.client_id:
        raise HTTPException(
            403, "Las versiones internas no están disponibles en el portal."
        )
    return [
        serial(v)
        for v in db.scalars(
            select(ProposalVersion)
            .where(ProposalVersion.proposal_id == p.id)
            .order_by(ProposalVersion.version)
        )
    ]


@router.post("/{pid}/assign")
def assign(
    pid: str,
    body: Assignment,
    request: Request,
    u=Depends(current_user),
    db=Depends(get_db),
):
    require(db, u, "assignment.manage")
    if u.client_id:
        raise HTTPException(403, "La asignación es exclusiva del equipo interno.")
    p = proposal_access(db, u, pid, True)
    if p.state not in {"in_analysis", "reanalysis", "additional_requested"}:
        raise HTTPException(
            409, "La asignación requiere un expediente enviado a Riesgos."
        )
    users = []
    for aid in set(body.analyst_ids):
        v = db.get(User, aid)
        if (
            not v
            or not v.active
            or v.client_id
            or "risk.view" not in permissions(db, v)
        ):
            raise HTTPException(
                422, "Todos los participantes deben ser analistas activos."
            )
        if "portfolio.all" not in permissions(db, u) and v.supervisor_id != u.id:
            raise HTTPException(403, "Solo puede asignar analistas de su equipo.")
        users.append(v)
    previous = []
    for a in db.scalars(
        select(AnalystAssignment).where(
            AnalystAssignment.proposal_id == pid, AnalystAssignment.active.is_(True)
        )
    ):
        previous.append(a.user_id)
        a.active = False
    for v in users:
        db.add(
            AnalystAssignment(
                proposal_id=pid, user_id=v.id, assigned_by=u.id, reason=body.reason
            )
        )
    record(
        db,
        u,
        "assignment.change",
        pid,
        before={"analysts": previous},
        after={"analysts": [v.id for v in users], "reason": body.reason},
        request=request,
    )
    notify(
        db,
        p,
        "Nueva propuesta asignada",
        "Tiene un expediente pendiente de análisis.",
        client_visible=False,
        extra_users=[v.id for v in users],
    )
    db.commit()
    return proposal_dict(db, p, u)


@router.post("/{pid}/report")
def save_report(
    pid: str,
    body: ReportInput,
    request: Request,
    u=Depends(current_user),
    db=Depends(get_db),
):
    require(db, u, "proposal.edit")
    p = proposal_access(db, u, pid, True)
    check_manager(db, u, p)
    if p.state not in EDITABLE:
        raise HTTPException(409, "El informe está bloqueado durante el análisis.")
    r = db.scalar(select(CommercialReport).where(CommercialReport.proposal_id == pid))
    if r:
        if body.version is not None and body.version != r.version:
            raise HTTPException(409, "El informe cambió. Actualice antes de guardar.")
        r.version += 1
    else:
        r = CommercialReport(proposal_id=pid, author_id=u.id)
        db.add(r)
        db.flush()
    r.content = body.content
    r.final = body.final
    r.author_id = u.id
    from .quality import automatic_assessment

    r.ai_assessment = automatic_assessment(
        db, body.content, db.get(Client, p.client_id)
    )
    if body.human_assessment is not None:
        require(db, u, "report.assess")
        from .quality import human_assessment

        r.human_assessment = human_assessment(db, body.human_assessment, u)
    db.add(
        CommercialReportVersion(
            report_id=r.id,
            actor_id=u.id,
            content=r.content,
            version=r.version,
            origin="human",
            final=r.final,
        )
    )
    record(
        db,
        u,
        "report.save",
        r.id,
        after={"version": r.version, "final": r.final, "origin": "human"},
        request=request,
    )
    db.commit()
    return serial(r)


@router.post("/{pid}/report/assist")
def assist_report(
    pid: str, request: Request, u=Depends(current_user), db=Depends(get_db)
):
    require(db, u, "proposal.edit")
    p = proposal_access(db, u, pid, True)
    check_manager(db, u, p)
    if p.state not in EDITABLE:
        raise HTTPException(409, "El informe está bloqueado durante el análisis.")
    from .ai import commercial_assistance

    c = db.get(Client, p.client_id)
    texts = [
        d.extraction.get("text", "")
        for d in db.scalars(
            select(Document)
            .join(ProposalRequirement)
            .where(ProposalRequirement.proposal_id == pid, Document.deleted.is_(False))
        )
    ]
    try:
        result = commercial_assistance(serial(c), serial(p), texts)
    except Exception:
        raise HTTPException(
            503,
            "La asistencia no está disponible temporalmente. Puede continuar redactando el informe.",
        )
    r = db.scalar(select(CommercialReport).where(CommercialReport.proposal_id == pid))
    if not r:
        r = CommercialReport(proposal_id=pid, author_id=u.id)
        db.add(r)
        db.flush()
    else:
        r.version += 1
    r.ai_content = result["content"]
    r.ai_assessment = result.get("assessment", {})
    r.final = False
    from .quality import automatic_assessment

    r.ai_assessment = {
        **automatic_assessment(db, r.ai_content, c),
        "provider": result.get("provider"),
        "financial_signals": result.get("assessment", {}),
    }
    db.add(
        CommercialReportVersion(
            report_id=r.id,
            actor_id=u.id,
            content=r.ai_content,
            version=r.version,
            origin="ai",
            final=False,
        )
    )
    record(
        db,
        u,
        "report.ai_generated",
        r.id,
        after={"provider": result.get("provider"), "version": r.version},
        request=request,
    )
    db.commit()
    return serial(r)


@router.get("/{pid}/comments")
def comments(pid: str, u=Depends(current_user), db=Depends(get_db)):
    p = proposal_access(db, u, pid)
    if u.client_id:
        raise HTTPException(403, "La conversación es privada del equipo interno.")
    return [
        {
            **serial(c),
            "author_name": db.get(User, c.author_id).name,
            "attachments": [
                serial(a)
                for a in db.scalars(
                    select(Attachment).where(Attachment.comment_id == c.id)
                )
            ],
        }
        for c in db.scalars(
            select(Comment)
            .where(Comment.proposal_id == pid, Comment.deleted.is_(False))
            .order_by(Comment.created_at)
        )
    ]


@router.post("/{pid}/comments", status_code=201)
def comment(
    pid: str,
    body: CommentInput,
    request: Request,
    u=Depends(current_user),
    db=Depends(get_db),
):
    require(db, u, "comment.write")
    p = proposal_access(db, u, pid)
    if u.client_id:
        raise HTTPException(403, "La conversación es privada del equipo interno.")
    c = Comment(proposal_id=pid, author_id=u.id, content=body.content)
    db.add(c)
    db.flush()
    for did in body.attachment_ids:
        d = db.get(Document, did)
        if (
            not d
            or d.deleted
            or db.get(ProposalRequirement, d.requirement_id).proposal_id != pid
        ):
            raise HTTPException(422, "El adjunto no pertenece al expediente.")
        db.add(Attachment(comment_id=c.id, document_id=did))
    record(
        db,
        u,
        "comment.create",
        c.id,
        after={
            "proposal_id": pid,
            "content": c.content,
            "attachment_ids": body.attachment_ids,
        },
        request=request,
    )
    notify(
        db,
        p,
        "Nuevo comentario interno",
        "El equipo agregó un comentario al expediente.",
        client_visible=False,
    )
    db.commit()
    return {**serial(c), "author_name": u.name}


@router.patch("/{pid}/comments/{cid}")
def edit_comment(
    pid: str,
    cid: str,
    body: CommentInput,
    request: Request,
    u=Depends(current_user),
    db=Depends(get_db),
):
    require(db, u, "comment.write")
    proposal_access(db, u, pid)
    c = db.scalar(
        select(Comment)
        .where(
            Comment.id == cid, Comment.proposal_id == pid, Comment.deleted.is_(False)
        )
        .with_for_update()
    )
    if not c or c.author_id != u.id or u.client_id:
        raise HTTPException(403, "Solo el autor puede editar su mensaje.")
    before = serial(c)
    c.content = body.content
    c.version += 1
    record(db, u, "comment.edit", cid, before=before, after=serial(c), request=request)
    db.commit()
    return serial(c)


@router.delete("/{pid}/comments/{cid}")
def delete_comment(
    pid: str, cid: str, request: Request, u=Depends(current_user), db=Depends(get_db)
):
    require(db, u, "comment.write")
    proposal_access(db, u, pid)
    c = db.get(Comment, cid)
    if not c or c.proposal_id != pid or c.author_id != u.id or u.client_id:
        raise HTTPException(403, "Solo el autor puede retirar su mensaje.")
    before = serial(c)
    c.deleted = True
    record(
        db, u, "comment.delete", cid, before=before, after=serial(c), request=request
    )
    db.commit()
    return {"message": "Mensaje retirado. La acción permanece en auditoría."}


@router.post("/{pid}/report/assessment")
def assess_report(
    pid: str,
    request: Request,
    scores: dict = __import__("fastapi").Body(...),
    u=Depends(current_user),
    db=Depends(get_db),
):
    require(db, u, "report.assess")
    if u.client_id:
        raise HTTPException(403, "La evaluación es interna.")
    p = proposal_access(db, u, pid, True)
    r = db.scalar(select(CommercialReport).where(CommercialReport.proposal_id == pid))
    if not r:
        raise HTTPException(404, "El informe todavía no fue elaborado.")
    from .quality import human_assessment

    r.human_assessment = human_assessment(db, scores, u)
    record(
        db,
        u,
        "report.human_assessment",
        r.id,
        after=r.human_assessment,
        request=request,
    )
    db.commit()
    return serial(r)
