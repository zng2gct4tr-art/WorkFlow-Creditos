"""API integration with PostgreSQL; scan/storage/broker are explicitly mocked boundaries.
Actual ClamAV, S3 and worker connectivity need independent infrastructure validation.
"""

import io
from uuid import uuid4
from unittest.mock import Mock
import pytest
from sqlalchemy import select


@pytest.fixture
def upload_boundaries(monkeypatch):
    import app.documents as docs
    from app.worker import process_document

    scan = Mock()
    store = Mock()
    dispatch = Mock()
    monkeypatch.setattr(docs, "scan_file", scan)
    monkeypatch.setattr(docs, "storage_put", store)
    monkeypatch.setattr(process_document, "delay", dispatch)
    return scan, store, dispatch


def pdf_bytes(text):
    from reportlab.pdfgen import canvas

    data = io.BytesIO()
    pdf = canvas.Canvas(data)
    pdf.drawString(50, 750, text)
    pdf.save()
    return data.getvalue()


def upload(client, rid, data, **form):
    return client.post(
        f"/api/requirements/{rid}/documents",
        files={"file": ("document.pdf", data, "application/pdf")},
        data=form,
    )


def test_upload_mime_rejection_storage_failure_and_replacement(case, upload_boundaries):
    manager, _, p, _ = case
    rid = p["requirements"][0]["id"]
    scan, store, dispatch = upload_boundaries
    assert upload(manager, rid, b"pretending PDF").status_code == 422
    scan.assert_not_called()
    store.assert_not_called()
    store.side_effect = RuntimeError("unavailable")
    assert upload(manager, rid, pdf_bytes("Storage unavailable")).status_code == 503
    from app.db import SessionLocal
    from app.models import Document, AuditEvent

    with SessionLocal() as db:
        assert (
            list(db.scalars(select(Document).where(Document.requirement_id == rid)))
            == []
        )
    store.side_effect = None
    first = upload(manager, rid, pdf_bytes("Original statement"))
    assert first.status_code == 201, first.text
    old = first.json()
    assert old["status"] == "uploaded"
    replacement = upload(
        manager, rid, pdf_bytes("Replacement statement"), replace_id=old["id"]
    )
    assert replacement.status_code == 201, replacement.text
    with SessionLocal() as db:
        assert db.get(Document, old["id"]).deleted
        assert (
            db.scalar(
                select(AuditEvent).where(
                    AuditEvent.action == "document.replace",
                    AuditEvent.resource == old["id"],
                )
            )
            is not None
        )
    assert manager.get(f"/api/documents/{old['id']}").status_code == 404
    detail = manager.get(f"/api/proposals/{p['id']}").json()
    assert detail["completeness"] < 100 and not detail["validity"]
    assert len(detail["requirements"][0]["documents"]) == 1
    assert dispatch.call_count == 2


def test_unresolved_ocr_failure_cannot_be_marked_correct(
    case, login, upload_boundaries
):
    manager, _, p, _ = case
    result = upload(manager, p["requirements"][0]["id"], pdf_bytes("Unresolved OCR"))
    assert result.status_code == 201
    did = result.json()["id"]
    admin = login("admin")
    from app.db import SessionLocal
    from app.models import Document

    for status in ["uploaded", "processing", "processing_failed"]:
        with SessionLocal() as db:
            db.get(Document, did).status = status
            db.commit()
        response = admin.post(
            f"/api/documents/{did}/validate",
            json={"status": "correct", "reason": "Cannot bypass unresolved extraction"},
        )
        assert response.status_code == 409, (status, response.text)


def test_signed_download_denies_tamper_expiration_and_other_session(
    case, login, upload_boundaries, monkeypatch
):
    import app.documents as docs
    from app.download_tokens import token_for
    from app.models import Session
    from app.security import digest
    from app.db import SessionLocal

    manager, _, p, _ = case
    content = pdf_bytes("Session bound document")
    response = upload(manager, p["requirements"][0]["id"], content)
    assert response.status_code == 201
    did = response.json()["id"]
    monkeypatch.setenv("STORAGE_PROVIDER", "azure")
    get = Mock(side_effect=lambda key, path: path.write_bytes(content))
    monkeypatch.setattr(docs, "storage_get", get)
    response = manager.get(f"/api/documents/{did}/download-url")
    assert response.status_code == 200, response.text
    url = response.json()["url"]
    assert manager.get(url).status_code == 200
    other = login("manager")
    assert other.get(url).status_code == 403
    get.reset_mock()
    assert manager.get(url[:-1] + ("0" if url[-1] != "0" else "1")).status_code == 403
    with SessionLocal() as db:
        session = db.scalar(
            select(Session).where(
                Session.token_hash == digest(manager.cookies["wf_session"])
            )
        )
        expired = token_for(did, session.user_id, session.id, ttl=-1)
    assert (
        manager.get(
            f"/api/documents/{did}/content", params={"token": expired}
        ).status_code
        == 403
    )
    get.assert_not_called()
