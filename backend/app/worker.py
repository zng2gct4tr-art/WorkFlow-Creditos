"""Task entrypoints; document payloads never travel through broker messages."""

import os
from celery import Celery

if os.getenv("WORKFLOW_DESKTOP") == "1":
    from .desktop_queue import DesktopQueue

    celery_app = DesktopQueue()
else:
    celery_app = Celery(
        "workflow",
        broker=os.getenv("REDIS_URL", "redis://redis:6379/0"),
        backend=os.getenv("REDIS_URL", "redis://redis:6379/0"),
    )
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_time_limit=600,
    task_soft_time_limit=540,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    result_expires=3600,
    beat_schedule={"sla-alerts": {"task": "workflow.sla_alerts", "schedule": 300.0}},
)


@celery_app.task(
    name="workflow.process_document",
    autoretry_for=(RuntimeError,),
    retry_backoff=True,
    max_retries=3,
)
def process_document(document_id):
    from .jobs import process_document as process

    return process(document_id)


@celery_app.task(
    name="workflow.send_email",
    autoretry_for=(OSError,),
    retry_backoff=True,
    max_retries=4,
)
def send_email(notification_id):
    from .jobs import send_email as send

    return send(notification_id)


@celery_app.task(name="workflow.sla_alerts")
def sla_alerts():
    from .jobs import check_sla

    return check_sla()


@celery_app.task(
    name="workflow.password_reset",
    autoretry_for=(OSError,),
    retry_backoff=True,
    max_retries=3,
    ignore_result=True,
)
def send_password_reset(user_id, token):
    from .jobs import send_password_reset as send

    return send(user_id, token)


@celery_app.task(
    name="workflow.audit_archive",
    autoretry_for=(OSError, RuntimeError),
    retry_backoff=True,
    max_retries=4,
)
def audit_archive():
    from .audit_archive import archive_audit

    return archive_audit()


celery_app.conf.beat_schedule["audit-archive"] = {
    "task": "workflow.audit_archive",
    "schedule": 60.0,
}
