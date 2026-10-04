"""Desktop pipeline with real PostgreSQL, durable queue, storage and PDF OCR.

Defender is the only mocked boundary because this test also runs on Linux.
Native Defender and the Windows installer have a separate release checklist.
"""

import base64
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time


def test_desktop_upload_worker_and_session_bound_download(case, tmp_path, monkeypatch):
    from app import documents, desktop_services, worker
    from app.desktop_queue import DesktopQueue
    from app.db import SessionLocal
    from app.models import Document
    from reportlab.pdfgen import canvas

    manager, client, proposal, _ = case
    monkeypatch.setenv("WORKFLOW_DESKTOP", "1")
    monkeypatch.setenv("STORAGE_PROVIDER", "local")
    monkeypatch.setenv("DESKTOP_STORAGE_PATH", str(tmp_path / "objects"))
    monkeypatch.setenv("DESKTOP_QUEUE_PATH", str(tmp_path / "queue.sqlite3"))
    monkeypatch.setenv(
        "STORAGE_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode()
    )
    monkeypatch.setenv("OCR_LANGUAGES", "eng")
    # Antivirus test double is explicit; no claim of Defender execution here.
    monkeypatch.setattr(documents, "scan_file", lambda _: None)
    monkeypatch.setattr(desktop_services, "defender_available", lambda: True)
    documents.ensure_bucket()
    queue = DesktopQueue()
    monkeypatch.setattr(worker, "celery_app", queue)

    @queue.task(name="workflow.process_document", max_retries=3)
    def task(document_id):
        raise AssertionError(
            "Must execute in the real child worker, not the HTTP process"
        )

    monkeypatch.setattr(worker, "process_document", task)
    source = tmp_path / "statement.pdf"
    page = canvas.Canvas(str(source))
    page.drawString(50, 750, f"RUT {client['rut']} Revenue 1000000 EBITDA 250000")
    page.save()
    uploaded = manager.post(
        f"/api/requirements/{proposal['requirements'][0]['id']}/documents",
        files={"file": (source.name, source.read_bytes(), "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["id"]
    child = subprocess.Popen(
        [sys.executable, "-m", "app.desktop_queue"],
        cwd=Path(__file__).resolve().parents[1],
        env=os.environ.copy(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            assert child.poll() is None, "Desktop worker exited"
            with SessionLocal() as db:
                document = db.get(Document, document_id)
                if document.status not in {
                    "uploaded",
                    "processing",
                    "processing_failed",
                }:
                    assert document.extraction
                    assert (
                        document.sha256
                        == hashlib.sha256(source.read_bytes()).hexdigest()
                    )
                    break
            time.sleep(0.2)
        else:
            raise AssertionError("Durable desktop queue did not finish real OCR")
        assert queue.available()
        assert manager.get("/api/ready").status_code == 200
        temporary_url = manager.get(f"/api/documents/{document_id}/download-url")
        assert temporary_url.status_code == 200
        download = manager.get(temporary_url.json()["url"])
        assert download.status_code == 200 and download.content == source.read_bytes()
        invalid = manager.get(temporary_url.json()["url"] + "tampered")
        assert invalid.status_code in {400, 403}
        assert len(list((tmp_path / "objects").iterdir())) == 1
    finally:
        child.terminate()
        child.wait(timeout=15)
