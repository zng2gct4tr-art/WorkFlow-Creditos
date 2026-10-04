"""Optional independently controlled S3 COMPLIANCE archive for DB-admin tamper resistance.
The bucket must already have Object Lock enabled; failures are never treated as success.
"""

import os, json
from datetime import timedelta
from sqlalchemy import select
from .db import SessionLocal
from .models import AuditEvent, Setting, now
from .domain import serial


def archive_audit():
    bucket = os.getenv("AUDIT_ARCHIVE_BUCKET")
    if not bucket:
        return {"configured": False}
    from .documents import _storage

    storage = _storage()
    retention = int(os.getenv("AUDIT_RETENTION_DAYS", "2555"))
    if retention < 1:
        raise RuntimeError("Audit retention must be positive")
    lock = storage.get_object_lock_configuration(Bucket=bucket)
    if lock.get("ObjectLockConfiguration", {}).get("ObjectLockEnabled") != "Enabled":
        raise RuntimeError("Audit archive requires Object Lock")
    with SessionLocal() as db:
        marker = db.get(Setting, "audit_archive_checkpoint")
        last = (marker.value if marker else {}).get("last_id", 0)
        events = list(
            db.scalars(
                select(AuditEvent)
                .where(AuditEvent.id > last)
                .order_by(AuditEvent.id)
                .limit(1000)
            )
        )
        for event in events:
            storage.put_object(
                Bucket=bucket,
                Key=f"audit/{event.id:020d}-{event.hash}.json",
                Body=json.dumps(serial(event), ensure_ascii=False).encode(),
                ContentType="application/json",
                ServerSideEncryption="AES256",
                ObjectLockMode="COMPLIANCE",
                ObjectLockRetainUntilDate=now() + timedelta(days=retention),
            )
        if events:
            value = {
                "last_id": events[-1].id,
                "hash": events[-1].hash,
                "archived_at": now().isoformat(),
            }
            if marker:
                marker.value = value
            else:
                db.add(Setting(key="audit_archive_checkpoint", value=value))
            db.commit()
        return {"archived": len(events)}
