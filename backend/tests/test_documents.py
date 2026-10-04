"""Real libmagic/container checks; these tests do not claim antivirus/S3 integration."""

import zipfile
import pytest


def test_mime_spoof_and_empty_rejected(tmp_path):
    from app.documents import inspect_upload

    path = tmp_path / "fake.pdf"
    path.write_text("plain text pretending to be PDF")
    with pytest.raises(ValueError, match="contenido real"):
        inspect_upload(path, "fake.pdf", ["pdf"], 1000)
    path.write_bytes(b"")
    with pytest.raises(ValueError, match="vacío"):
        inspect_upload(path, "fake.pdf", ["pdf"], 1000)


def test_office_path_traversal_and_macro_rejected(tmp_path):
    from app.documents import inspect_office

    for name in ["../danger", "word/vbaProject.bin"]:
        path = tmp_path / "unsafe.docx"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("word/document.xml", "<document/>")
            archive.writestr(name, "unsafe")
        with pytest.raises(ValueError):
            inspect_office(path, "docx")


def test_real_pdf_signature_and_hash(tmp_path):
    from reportlab.pdfgen import canvas
    from app.documents import inspect_upload

    path = tmp_path / "document.pdf"
    pdf = canvas.Canvas(str(path))
    pdf.drawString(50, 750, "Financial statement")
    pdf.save()
    result = inspect_upload(path, "document.pdf", ["pdf"], 10000)
    assert result["mime"] == "application/pdf"
    assert len(result["sha256"]) == 64
    with pytest.raises(ValueError, match="límite"):
        inspect_upload(path, "document.pdf", ["pdf"], 1)


def test_real_pdf_text_extraction(tmp_path):
    from reportlab.pdfgen import canvas
    from app.ai import _local_text

    path = tmp_path / "statement.pdf"
    pdf = canvas.Canvas(str(path))
    pdf.drawString(50, 750, "Company RUT 123456789012 Revenue 1000000 EBITDA 250000")
    pdf.save()
    content, confidence = _local_text(path, "application/pdf")
    assert "123456789012" in content and "250000" in content
    assert confidence == 0.9


def test_aes_gcm_rejects_context_swap_key_swap_and_tampering(tmp_path, monkeypatch):
    import base64, os
    from cryptography.exceptions import InvalidTag
    from app.documents import _encrypt_file, _decrypt_file

    key = base64.b64encode(os.urandom(32)).decode()
    monkeypatch.setenv("STORAGE_ENCRYPTION_KEY", key)
    source = tmp_path / "plain"
    source.write_bytes(b"Private banking document\n" * 1000)
    ciphertext = tmp_path / "encrypted"
    _encrypt_file(source, ciphertext, b"proposal/objectA")
    destination = tmp_path / "restored"
    _decrypt_file(ciphertext, destination, b"proposal/objectA")
    assert destination.read_bytes() == source.read_bytes()
    destination.unlink()
    with pytest.raises(InvalidTag):
        _decrypt_file(ciphertext, destination, b"proposal/objectB")
    assert not destination.exists()
    monkeypatch.setenv(
        "STORAGE_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode()
    )
    with pytest.raises(InvalidTag):
        _decrypt_file(ciphertext, destination, b"proposal/objectA")
    assert not destination.exists()
    monkeypatch.setenv("STORAGE_ENCRYPTION_KEY", key)
    data = bytearray(ciphertext.read_bytes())
    data[30] ^= 1
    ciphertext.write_bytes(data)
    with pytest.raises(InvalidTag):
        _decrypt_file(ciphertext, destination, b"proposal/objectA")
    assert not destination.exists()
    assert not list(tmp_path.glob(".workflow-decrypt-*"))
