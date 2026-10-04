from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date
from zoneinfo import ZoneInfo
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError


def test_business_days_exclude_weekends_holidays():
    from app.sla import business_days

    tz = ZoneInfo("America/Montevideo")
    start = datetime(2026, 10, 2, 12, tzinfo=tz)
    end = datetime(2026, 10, 6, 12, tzinfo=tz)
    assert business_days(start, end, set()) == 2
    assert business_days(start, end, {date(2026, 10, 5)}) == 1
    assert business_days(end, start, set()) == 0


def test_audit_append_only_and_concurrent_chain(database):
    from app.db import SessionLocal
    from app.audit import record, verify_chain
    from app.models import AuditEvent

    def append(i):
        with SessionLocal() as db:
            record(db, None, "test.concurrent", str(i))
            db.commit()

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(append, range(12)))
    with SessionLocal() as db:
        events = list(db.scalars(select(AuditEvent).order_by(AuditEvent.id)))
        assert verify_chain(events)
    for statement in [
        "UPDATE audit_events SET action = action",
        "DELETE FROM audit_events",
        "TRUNCATE audit_events",
    ]:
        with SessionLocal() as db:
            with pytest.raises(DBAPIError, match="append-only"):
                db.execute(text(statement))
                db.commit()
            db.rollback()


def test_database_active_proposal_constraint(case):
    _, _, p, payload = case
    from app.db import SessionLocal
    from app.models import Proposal
    from uuid import uuid4

    with SessionLocal() as db:
        db.add(Proposal(code="TEST-" + uuid4().hex[:16], **payload))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_expired_document_blocks_completeness(case, valid_documents):
    from datetime import timedelta
    from app.db import SessionLocal
    from app.models import Document, Proposal, now
    from app.domain import completeness

    _, _, p, _ = case
    valid_documents(p)
    with SessionLocal() as db:
        document = db.scalar(
            select(Document).where(
                Document.requirement_id == p["requirements"][0]["id"]
            )
        )
        document.expires_at = now() - timedelta(days=1)
        db.commit()
        received, valid = completeness(db, db.get(Proposal, p["id"]))
        assert received == 100 and not valid


def test_closed_paused_sla_excludes_entire_pause_and_restart(case):
    from app.db import SessionLocal
    from app.models import SLARecord
    from app.sla import sla_view

    _, _, p, _ = case
    tz = ZoneInfo("America/Montevideo")
    with SessionLocal() as db:
        old = SLARecord(
            proposal_id=p["id"],
            area="risk",
            cycle=1,
            allowance=15,
            started_at=datetime(2026, 9, 7, 0, tzinfo=tz),
            paused_at=datetime(2026, 9, 9, 0, tzinfo=tz),
            ended_at=datetime(2026, 9, 28, 0, tzinfo=tz),
        )
        restart = SLARecord(
            proposal_id=p["id"],
            area="risk",
            cycle=1,
            allowance=15,
            started_at=datetime(2026, 9, 28, 0, tzinfo=tz),
            ended_at=datetime(2026, 9, 30, 0, tzinfo=tz),
        )
        db.add_all([old, restart])
        db.commit()
        paused = sla_view(db, old)
        new = sla_view(db, restart)
        assert (
            paused["consumed"] == 2 and not paused["paused"] and not paused["breached"]
        )
        assert new["consumed"] == 2 and new["remaining"] == 13
