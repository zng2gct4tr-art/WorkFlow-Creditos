import hashlib, json
from sqlalchemy import select, text
from .models import AuditEvent, now


def canonical(data):
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False
    )


def event_payload(e):
    return {
        "actor_id": e.actor_id,
        "action": e.action,
        "resource": e.resource,
        "before": e.before,
        "after": e.after,
        "ip": e.ip,
        "session_id": e.session_id,
        "created_at": e.created_at.isoformat(),
        "previous_hash": e.previous_hash,
    }


def record(db, actor, action, resource, before=None, after=None, request=None):
    # Serialize appends across transactions; prevent chain forks under concurrent workers.
    db.execute(text("SELECT pg_advisory_xact_lock(71263491)"))
    last = db.scalar(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(1))
    e = AuditEvent(
        actor_id=getattr(actor, "id", actor),
        action=action,
        resource=str(resource),
        before=before,
        after=after,
        created_at=now(),
        ip=request.client.host if request and request.client else "",
        session_id=getattr(request.state, "session_id", "") if request else "",
        previous_hash=last.hash if last else "0" * 64,
    )
    e.hash = hashlib.sha256(canonical(event_payload(e)).encode()).hexdigest()
    db.add(e)
    db.flush()
    return e


def verify_chain(events):
    previous = "0" * 64
    for e in events:
        if (
            e.previous_hash != previous
            or e.hash
            != hashlib.sha256(canonical(event_payload(e)).encode()).hexdigest()
        ):
            return False
        previous = e.hash
    return True
