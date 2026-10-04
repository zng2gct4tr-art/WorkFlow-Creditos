import os, tempfile, smtplib, logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from sqlalchemy import select
from .db import SessionLocal
from .models import *
from .audit import record
from .domain import serial, document_ready, notify
from .sla import sla_view

logger = logging.getLogger("workflow.jobs")


def process_document(document_id):
    from .documents import storage_get
    from .ai import analyze_document

    # Hold a document row lock across processing to make redelivery idempotent.
    with SessionLocal() as db:
        d = db.scalar(
            select(Document).where(Document.id == document_id).with_for_update()
        )
        if (
            not d
            or d.deleted
            or d.status not in {"uploaded", "processing", "processing_failed"}
        ):
            return {"skipped": True}
        r = db.get(ProposalRequirement, d.requirement_id)
        p = db.scalar(
            select(Proposal).where(Proposal.id == r.proposal_id).with_for_update()
        )
        c = db.get(Client, p.client_id)
        previous = d.status
        d.status = "processing"
        try:
            with tempfile.TemporaryDirectory(prefix="wf-ocr-") as directory:
                path = Path(directory) / d.name
                storage_get(d.storage_key, path)
                import hashlib

                with path.open("rb") as source:
                    if hashlib.file_digest(source, "sha256").hexdigest() != d.sha256:
                        raise RuntimeError("Document integrity failed")
                result = analyze_document(
                    path,
                    d.mime,
                    serial(c),
                    {**r.rules, "validity_days": r.validity_days},
                )
        except Exception:
            d.status = "processing_failed"
            d.observations = (
                "No se pudo completar el análisis. El sistema volverá a intentarlo."
            )
            record(
                db, None, "document.processing_failed", d.id, after={"status": d.status}
            )
            db.commit()
            logger.warning("document_processing_failed", extra={"document_id": d.id})
            raise RuntimeError("Document processing failed") from None
        d.extraction = result
        d.status = result.get("status", "review")
        d.observations = result.get("explanation", "")
        extracted = result.get("extracted", {})
        for name, aliases in [
            ("issued_at", ("issued_at", "issue_date")),
            ("expires_at", ("expires_at", "expiry_date")),
        ]:
            value = next((extracted.get(a) for a in aliases if extracted.get(a)), None)
            if value:
                try:
                    parsed = datetime.fromisoformat(str(value))
                    if name == "expires_at":
                        from zoneinfo import ZoneInfo

                        parsed = (parsed + timedelta(days=1)).replace(
                            tzinfo=ZoneInfo("America/Montevideo")
                        )
                    else:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    setattr(d, name, parsed)
                except (ValueError, TypeError):
                    pass
        db.add(
            AIValidation(
                document_id=d.id,
                provider=result.get("provider", "local"),
                result=result,
            )
        )
        db.add(
            DocumentValidation(
                document_id=d.id,
                actor_id=None,
                automatic=True,
                previous_status=previous,
                status=d.status,
                reason=d.observations
                or "Extracción automática; revisión humana requerida.",
            )
        )
        record(
            db,
            None,
            "document.ai_validation",
            d.id,
            before={"status": previous},
            after={
                "status": d.status,
                "provider": result.get("provider"),
                "failed_rules": result.get("failed_rules", []),
                "warnings": result.get("warnings", []),
            },
        )
        document_ready(db, p)
        if d.status == "incorrect":
            notify(
                db,
                p,
                "Documento rechazado",
                f"{r.name}: {d.observations}",
                client_visible=r.client_visible,
            )
        db.commit()
        return {"document_id": d.id, "status": d.status}


def smtp_send(destination, subject, body):
    host = os.environ.get("SMTP_HOST")
    if not host:
        raise RuntimeError("SMTP is not configured")
    message = EmailMessage()
    message["From"] = os.environ.get("SMTP_FROM", "workflow@localhost")
    message["To"] = destination
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(
        host, int(os.environ.get("SMTP_PORT", "587")), timeout=30
    ) as smtp:
        tls = os.environ.get("SMTP_TLS", "true").lower() == "true"
        if not tls and (
            os.getenv("APP_ENV", "development") == "production"
            or host not in {"localhost", "127.0.0.1", "mailpit"}
        ):
            raise RuntimeError("SMTP encryption required")
        if tls:
            smtp.starttls()
        if os.environ.get("SMTP_USERNAME"):
            smtp.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(message)


def send_email(notification_id):
    with SessionLocal() as db:
        n = db.scalar(
            select(Notification)
            .where(Notification.id == notification_id)
            .with_for_update()
        )
        if not n or n.email_status == "sent":
            return {"skipped": True}
        setting = db.get(Setting, "notifications")
        if (
            not setting
            or not setting.value.get("email_enabled")
            or not os.environ.get("SMTP_HOST")
        ):
            return {"configured": False}
        u = db.get(User, n.user_id)
        try:
            # Send no financial contents; user must authenticate to read details.
            smtp_send(
                u.email,
                "WorkFlow Créditos · " + n.title,
                "Tiene una nueva notificación en WorkFlow Créditos. Inicie sesión para consultar los detalles.",
            )
        except Exception:
            n.email_status = "failed"
            db.commit()
            raise OSError("Email dispatch failed") from None
        n.email_status = "sent"
        record(db, None, "notification.email_sent", n.id)
        db.commit()
        return {"sent": True}


def send_password_reset(user_id, token):
    from urllib.parse import quote

    with SessionLocal() as db:
        u = db.get(User, user_id)
        if not u or not u.active:
            return
        link = (
            os.environ.get("PUBLIC_ORIGIN", "http://localhost:3000").split(",")[0]
            + "/reset-password?token="
            + quote(token)
        )
        smtp_send(
            u.email,
            "Recuperar acceso a WorkFlow Créditos",
            "El enlace vence en 30 minutos y solo puede usarse una vez:\n" + link,
        )


def check_sla():
    from .worker import (
        process_document as dispatch_document,
        send_email as dispatch_email,
    )

    with SessionLocal() as db:
        for s in db.scalars(
            select(SLARecord)
            .where(SLARecord.ended_at.is_(None), SLARecord.paused_at.is_(None))
            .with_for_update(skip_locked=True)
        ):
            view = sla_view(db, s)
            color = view["color"]
            if color != "green" and s.alerted != color:
                p = db.get(Proposal, s.proposal_id)
                notify(
                    db,
                    p,
                    "SLA vencido" if color == "red" else "SLA próximo a vencer",
                    "Revise el expediente y su siguiente acción.",
                    client_visible=False,
                )
                record(
                    db,
                    None,
                    "sla.breached" if color == "red" else "sla.warning",
                    s.id,
                    after=view,
                )
                s.alerted = color
        db.commit()
        # Durable outbox: unprocessed uploads and email notifications survive process restarts.
        for did in db.scalars(
            select(Document.id)
            .where(
                Document.status.in_(["uploaded", "processing_failed"]),
                Document.deleted.is_(False),
            )
            .limit(100)
        ):
            dispatch_document.delay(did)
        for nid in db.scalars(
            select(Notification.id)
            .where(Notification.email_status.in_(["pending", "failed"]))
            .limit(100)
        ):
            dispatch_email.delay(nid)
    return {"checked": True}
