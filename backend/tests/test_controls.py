"""Security/control integration; archive S3 operations are explicitly mocked."""

import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from sqlalchemy import select


def test_configurable_quality_separates_human_and_automatic(case, login):
    manager, _, p, _ = case
    admin = login("admin")
    from app.db import SessionLocal
    from app.models import Setting
    from app.quality import KEYS

    with SessionLocal() as db:
        previous = dict(db.get(Setting, "rubric").value)
        custom = {key: 0 for key in KEYS}
        custom["analysis"] = 100
        db.get(Setting, "rubric").value = custom
        db.commit()
    try:
        response = manager.post(
            f"/api/proposals/{p['id']}/report",
            json={
                "content": "Empresa solicitud financiera riesgo conclusion EBITDA capacidad flujo deuda",
                "final": True,
            },
        )
        assert response.status_code == 200
        automatic = response.json()["ai_assessment"]
        assert (
            automatic["kind"] == "automatic"
            and automatic["weights"] == custom
            and automatic["score"] == 100
        )
        scores = {key: 50 for key in KEYS}
        scores["analysis"] = 80
        response = admin.post(
            f"/api/proposals/{p['id']}/report/assessment", json=scores
        )
        assert response.status_code == 200
        report = response.json()
        assert report["human_assessment"]["kind"] == "human"
        assert report["human_assessment"]["score"] == 80
        assert report["ai_assessment"] == automatic
        assert report["human_assessment"]["evaluator_id"] != report["author_id"]
        invalid = dict(scores, analysis=True)
        assert (
            admin.post(
                f"/api/proposals/{p['id']}/report/assessment", json=invalid
            ).status_code
            == 422
        )
    finally:
        with SessionLocal() as db:
            db.get(Setting, "rubric").value = previous
            db.commit()


@pytest.mark.parametrize(
    "override",
    [
        {"SESSION_SECRET": "short"},
        {"COOKIE_SECURE": "false"},
        {"PUBLIC_ORIGIN": "http://localhost"},
    ],
)
def test_production_rejects_unsafe_configuration(override):
    env = dict(
        os.environ,
        APP_ENV="production",
        SESSION_SECRET="x" * 40,
        COOKIE_SECURE="true",
        PUBLIC_ORIGIN="https://bank.example",
    )
    env.update(override)
    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode != 0
    assert "Production requires" in result.stderr


def test_production_hides_docs_and_secure_headers():
    env = dict(
        os.environ,
        APP_ENV="production",
        SESSION_SECRET="x" * 40,
        COOKIE_SECURE="true",
        PUBLIC_ORIGIN="https://bank.example",
    )
    script = "from app.main import app; from fastapi.testclient import TestClient; c=TestClient(app); assert c.get('/api/docs').status_code==404; r=c.get('/api/health'); assert r.status_code==200; assert r.headers['Strict-Transport-Security'].startswith('max-age=31536000'); assert r.headers['X-Content-Type-Options']=='nosniff'"
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=env
    )
    assert result.returncode == 0, result.stderr


def test_archive_requires_objectlock_and_compliance_retention(database, monkeypatch):
    from app.db import SessionLocal
    from app.models import Setting
    from app.audit_archive import archive_audit
    import app.documents as documents

    storage = Mock()
    monkeypatch.setattr(documents, "_storage", lambda: storage)
    monkeypatch.setenv("AUDIT_ARCHIVE_BUCKET", "test-independent-audit")
    monkeypatch.setenv("AUDIT_RETENTION_DAYS", "2555")
    storage.get_object_lock_configuration.return_value = {
        "ObjectLockConfiguration": {"ObjectLockEnabled": "Disabled"}
    }
    with pytest.raises(RuntimeError, match="Object Lock"):
        archive_audit()
    storage.put_object.assert_not_called()
    storage.get_object_lock_configuration.return_value = {
        "ObjectLockConfiguration": {"ObjectLockEnabled": "Enabled"}
    }
    with SessionLocal() as db:
        marker = db.get(Setting, "audit_archive_checkpoint")
        original = dict(marker.value) if marker else None
        if marker:
            db.delete(marker)
            db.commit()
    try:
        result = archive_audit()
        assert result["archived"] > 0
        for call in storage.put_object.call_args_list:
            assert call.kwargs["ObjectLockMode"] == "COMPLIANCE"
            assert call.kwargs["ServerSideEncryption"] == "AES256"
            assert call.kwargs["Bucket"] == "test-independent-audit"
            assert b"previous_hash" in call.kwargs["Body"]
        # Persistent test data may span several 1,000-event batches.
        from sqlalchemy import func
        from app.models import AuditEvent

        with SessionLocal() as db:
            total = db.scalar(select(func.count()).select_from(AuditEvent))
        for _ in range(total // 1000 + 1):
            if archive_audit()["archived"] == 0:
                break
        else:
            raise AssertionError("Archive checkpoint did not catch up")
        count = storage.put_object.call_count
        assert archive_audit()["archived"] == 0
        assert storage.put_object.call_count == count
    finally:
        with SessionLocal() as db:
            marker = db.get(Setting, "audit_archive_checkpoint")
            if original is None:
                if marker:
                    db.delete(marker)
            elif marker:
                marker.value = original
            else:
                db.add(Setting(key="audit_archive_checkpoint", value=original))
            db.commit()
