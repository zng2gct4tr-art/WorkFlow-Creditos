"""Opt-in integration: REAL PostgreSQL, Redis/Celery, Blob, ClamAV, OCR and SMTP.
Run from repository root with .venv/bin/python backend/tests/integration_real_services.py.
Only creates test data in a database whose name ends _test. No external messages.
"""

import os, sys, time, subprocess, io, tempfile, secrets, hashlib, json
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from dotenv import dotenv_values
from sqlalchemy import create_engine, text, select
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
os.environ.update(
    {k: v for k, v in dotenv_values(ROOT / ".env").items() if v is not None}
)
url = make_url(os.getenv("REAL_TEST_DATABASE_URL", os.environ["DATABASE_URL"])).set(
    database="workflow_real_services_test"
)
database_name = url.database
if not url.database.endswith("_test"):
    raise SystemExit("Refusing non-test database")
os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
os.environ["REDIS_URL"] = "redis://localhost:6379/11"
os.environ["COOKIE_SECURE"] = "false"
os.environ["PUBLIC_ORIGIN"] = "http://localhost:3000"
os.environ["SMTP_HOST"] = "localhost"
os.environ["SMTP_PORT"] = "1025"
os.environ["SMTP_TLS"] = "false"
os.environ["APP_ENV"] = "development"
engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
with engine.connect() as connection:
    if not connection.execute(
        text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": url.database}
    ).scalar():
        connection.exec_driver_sql(f"CREATE DATABASE {url.database}")
engine.dispose()
subprocess.run(
    [sys.executable, "-m", "alembic", "upgrade", "head"],
    cwd=ROOT / "backend",
    check=True,
)
sys.path.insert(0, str(ROOT / "backend"))
from app.bootstrap import bootstrap

bootstrap()
from app.db import SessionLocal
from app.models import Role, User, Setting, Document, Notification, AuditEvent, now
from app.security import password_hash
from app.documents import ensure_bucket, _azure_container
from app.main import app
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from app.worker import send_email
from app.audit import verify_chain

ensure_bucket()
uid = uuid4().hex
with SessionLocal() as db:
    roles = {r.name: r.id for r in db.scalars(select(Role))}
    people = {}
    for key, role in [
        ("manager", "GESTOR COMERCIAL"),
        ("analyst", "ANALISTA"),
        ("admin", "ADMINISTRADOR"),
    ]:
        user = User(
            name="QA " + key,
            email=f"{key}-{uid}@example.com",
            role_ids=[roles[role]],
            password_hash=password_hash("RealIntegration123!"),
        )
        db.add(user)
        db.flush()
        people[key] = {"id": user.id, "email": user.email}
    db.get(Setting, "notifications").value = {"email_enabled": True, "warning_days": 1}
    db.commit()


def request(client, method, path, **kwargs):
    response = getattr(client, method)(path, **kwargs)
    assert response.status_code in (200, 201, 204), (
        path,
        response.status_code,
        response.text[:500],
    )
    return response


def login(email):
    c = TestClient(app, base_url="http://localhost")
    result = request(
        c,
        "post",
        "/api/auth/login",
        json={"email": email, "password": "RealIntegration123!"},
    ).json()
    c.headers["X-CSRF-Token"] = result["csrf_token"]
    return c


manager = login(people["manager"]["email"])
admin = login(people["admin"]["email"])
catalog = request(manager, "get", "/api/catalog").json()
rut = str(uuid4().int)[:12]
company = request(
    manager,
    "post",
    "/api/clients",
    json={
        "name": "QA Real Services " + uid[:8],
        "rut": rut,
        "account_number": uid,
        "manager_id": people["manager"]["id"],
        "profile_id": catalog["profiles"][0]["id"],
        "financials": {"revenue": 1000000, "ebitda": 200000, "total_debt": 300000},
    },
).json()
customer = request(
    admin,
    "post",
    "/api/admin/users",
    json={
        "name": "QA portal",
        "email": f"portal-{uid}@example.com",
        "password": "RealIntegration123!",
        "role_ids": [roles["CLIENTE"]],
        "client_id": company["id"],
    },
).json()
portal = login(customer["email"])
p = request(
    manager,
    "post",
    "/api/proposals",
    json={
        "client_id": company["id"],
        "product_id": catalog["products"][0]["id"],
        "amount": "50000",
        "currency": "UYU",
        "term_months": 12,
        "purpose": "Prueba real aislada de servicios",
    },
).json()


def pdf(name, wrong=False):
    output = io.BytesIO()
    c = canvas.Canvas(output)
    lines = [
        company["name"],
        "RUT: " + ("999999999999" if wrong else rut),
        "Documento: " + name,
        "Emision: 2026-10-03",
        "Vencimiento: 2027-10-03",
        "Ejercicio financiero 2026",
        "Facturacion UYU 1000000",
        "EBITDA UYU 200000",
        "Deuda total UYU 300000",
    ]
    for i, line in enumerate(lines):
        c.drawString(40, 800 - i * 24, line)
    c.save()
    return output.getvalue()


def upload(requirement, wrong=False, replace=None):
    raw = pdf(requirement["name"] + (" incorrecto" if wrong else " vigente"), wrong)
    response = request(
        portal,
        "post",
        f"/api/requirements/{requirement['id']}/documents",
        files={"file": ("documento.pdf", raw, "application/pdf")},
        data={"replace_id": replace} if replace else {},
    )
    assert "extraction" not in response.json()
    return response.json(), raw


def await_doc(doc):
    for attempt in range(80):
        result = request(manager, "get", f"/api/documents/{doc['id']}").json()
        if result["status"] not in {"uploaded", "processing", "processing_failed"}:
            return result
        time.sleep(0.5)
    raise AssertionError("Actual OCR worker did not complete")


def move(actor, action, **extra):
    current = request(manager, "get", f"/api/proposals/{p['id']}").json()
    return request(
        actor,
        "post",
        f"/api/proposals/{p['id']}/transition",
        json={
            "action": action,
            "version": current["version"],
            "reason": "Justificación de prueba controlada de extremo a extremo",
            **extra,
        },
    ).json()


log = open("/tmp/workflow-real-worker.log", "w")
worker = subprocess.Popen(
    [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "app.worker:celery_app",
        "worker",
        "--pool=solo",
        "--loglevel=warning",
    ],
    cwd=ROOT / "backend",
    env=os.environ.copy(),
    stdout=log,
    stderr=subprocess.STDOUT,
)
try:
    docs = []
    for i, r in enumerate(p["requirements"]):
        d, raw = upload(r, wrong=i == 0)
        result = await_doc(d)
        if i == 0:
            assert result["status"] == "incorrect", result
            assert result["extraction"]["failed_rules"]
            d, raw = upload(r, replace=d["id"])
            result = await_doc(d)
        assert result["status"] == "review", result
        assert rut in result["extraction"]["extracted"]["ruts"]
        request(
            manager,
            "post",
            f"/api/documents/{d['id']}/validate",
            json={
                "status": "correct",
                "reason": "Identidad, vigencia y datos comprobados en documento de prueba.",
            },
        )
        url = request(portal, "get", f"/api/documents/{d['id']}/download-url").json()[
            "url"
        ]
        binary = request(portal, "get", url).content
        assert hashlib.sha256(binary).digest() == hashlib.sha256(raw).digest()
        assert (
            portal.get(f"/api/documents/{d['id']}/content?token=invalid").status_code
            == 403
        )
        with SessionLocal() as db:
            stored = db.get(Document, d["id"])
            ciphertext = _azure_container().download_blob(stored.storage_key).readall()
            assert ciphertext.startswith(b"WFENC1") and raw[:100] not in ciphertext
        docs.append(d)
    current = request(manager, "get", f"/api/proposals/{p['id']}").json()
    assert (
        current["completeness"] == 100
        and current["validity"] is True
        and current["sla"]["commercial"]["allowance"] == 7
    )
    assistance = request(
        manager, "post", f"/api/proposals/{p['id']}/report/assist"
    ).json()
    assert (
        assistance["ai_assessment"]["financial_signals"]["financial_metrics"][
            "debt_to_ebitda"
        ]
        == 1.5
    )
    request(
        manager,
        "post",
        f"/api/proposals/{p['id']}/report",
        json={
            "content": assistance["ai_content"]
            + "\nOpinión humana: capacidad de pago y riesgos contrastados.",
            "final": True,
        },
    )
    move(manager, "prepare")
    submitted = move(manager, "submit")
    assert (
        submitted["sla"]["commercial"]["ended_at"]
        and submitted["sla"]["risk"]["allowance"] == 15
    )
    request(
        admin,
        "post",
        f"/api/proposals/{p['id']}/assign",
        json={
            "analyst_ids": [people["analyst"]["id"]],
            "reason": "Asignación manual por supervisor de prueba",
        },
    )
    analyst = login(people["analyst"]["email"])
    requested = move(
        analyst, "request_information", requirements=["Flujo de caja actualizado"]
    )
    assert requested["sla"]["risk"]["paused"]
    r = requested["requirements"][-1]
    d, raw = upload(r)
    assert await_doc(d)["status"] == "review"
    request(
        manager,
        "post",
        f"/api/documents/{d['id']}/validate",
        json={
            "status": "correct",
            "reason": "Flujo de caja contrastado en revisión autorizada.",
        },
    )
    resumed = move(manager, "resubmit")
    assert (
        not resumed["sla"]["risk"]["paused"] and resumed["sla"]["risk"]["consumed"] == 0
    )
    extra = analyst.post(
        f"/api/proposals/{p['id']}/transition",
        json={
            "action": "request_information",
            "version": resumed["version"],
            "reason": "Segunda solicitud prohibida",
        },
    )
    assert extra.status_code == 409
    approved = move(analyst, "approve")
    assert approved["state"] == "approved"
    assert (
        request(portal, "get", f"/api/proposals/{p['id']}").json()["state"]
        == "approved"
    )
    assert (
        request(manager, "get", "/api/reports/dashboard").json()["by_state"]["approved"]
        >= 1
    )
    for format, signature in [
        ("csv", b"\xef\xbb\xbf"),
        ("xlsx", b"PK"),
        ("pdf", b"%PDF"),
    ]:
        assert request(
            manager, "get", "/api/reports/export?format=" + format
        ).content.startswith(signature)
    with SessionLocal() as db:
        events = list(db.scalars(select(AuditEvent).order_by(AuditEvent.id)))
        assert verify_chain(events)
        for n in db.scalars(
            select(Notification).where(Notification.proposal_id == p["id"])
        ):
            send_email.delay(n.id)
    import httpx

    for _ in range(40):
        inbox = httpx.get("http://localhost:8025/api/v1/messages").json()
        if inbox["total"] > 0:
            break
        time.sleep(0.25)
    assert inbox["total"] > 0, "SMTP local did not receive notifications"
    print(
        json.dumps(
            {
                "result": "passed",
                "database": database_name,
                "steps": [
                    "real_clamav",
                    "private_encrypted_blob",
                    "actual_ocr_detects_wrong_rut",
                    "customer_replacement",
                    "human_review",
                    "signed_authenticated_download",
                    "commercial_sla",
                    "commercial_report",
                    "risk_assignment",
                    "single_information_request",
                    "risk_sla_restart",
                    "approval",
                    "customer_notification",
                    "dashboard",
                    "csv_xlsx_pdf",
                    "immutable_audit",
                    "real_local_smtp",
                ],
                "documents": len(docs) + 1,
                "mailbox_received": inbox["total"],
            },
            ensure_ascii=False,
        )
    )
finally:
    worker.terminate()
    try:
        worker.wait(timeout=10)
    except subprocess.TimeoutExpired:
        worker.kill()
        worker.wait()
    log.close()
