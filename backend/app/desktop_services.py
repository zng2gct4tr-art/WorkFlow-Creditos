"""Native Windows adapters. Missing/disabled Defender always blocks uploads."""

import json
import os
from pathlib import Path
import subprocess


def _powershell(script):
    root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    exe = root / "System32/WindowsPowerShell/v1.0/powershell.exe"
    result = subprocess.run(
        [str(exe), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        timeout=30,
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return json.loads(result.stdout.decode("utf-8-sig"))


def defender_available():
    if os.name != "nt":
        raise RuntimeError("Microsoft Defender requiere Windows.")
    try:
        status = _powershell(
            "$ErrorActionPreference='Stop'; "
            "Get-MpComputerStatus | Select-Object AMServiceEnabled,AntivirusEnabled,"
            "RealTimeProtectionEnabled,AntivirusSignatureAge | ConvertTo-Json -Compress"
        )
        if (
            not all(
                status.get(k) is True
                for k in (
                    "AMServiceEnabled",
                    "AntivirusEnabled",
                    "RealTimeProtectionEnabled",
                )
            )
            or not isinstance(status.get("AntivirusSignatureAge"), int)
            or not 0 <= status["AntivirusSignatureAge"] <= 7
        ):
            raise ValueError("Defender no disponible o firmas desactualizadas")
        defender_executable()
    except Exception:
        raise RuntimeError(
            "Análisis antimalware no disponible; active y actualice Microsoft Defender."
        ) from None
    return True


def defender_executable():
    # Never trust PATH or a user-selected scanner executable.
    base = (
        Path(os.environ.get("ProgramData", r"C:\ProgramData"))
        / "Microsoft/Windows Defender/Platform"
    )
    candidates = sorted(base.glob("*/MpCmdRun.exe"), reverse=True)
    fallback = (
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Windows Defender/MpCmdRun.exe"
    )
    for exe in candidates + [fallback]:
        if exe.is_file():
            return exe
    raise RuntimeError("Microsoft Defender no disponible.")


def scan_defender(path):
    try:
        defender_available()
        result = subprocess.run(
            [
                str(defender_executable()),
                "-Scan",
                "-ScanType",
                "3",
                "-File",
                str(Path(path).resolve()),
                "-DisableRemediation",
            ],
            capture_output=True,
            timeout=180,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            raise RuntimeError(
                "Documento rechazado por el análisis antimalware o fallo del antivirus."
            )
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError(
            "Análisis antimalware no disponible; carga bloqueada."
        ) from None


def desktop_mime(path, extension):
    """Parse real file content, avoiding a separate libmagic DLL on Windows."""
    from PIL import Image
    import zipfile

    with open(path, "rb") as file:
        header = file.read(1024)
    if extension == "pdf" and header.startswith(b"%PDF-"):
        # Poppler validates structure during extraction; signature alone is not
        # a security sandbox. Every upload still passes antivirus first.
        return "application/pdf"
    if extension in {"png", "jpg", "jpeg"}:
        try:
            with Image.open(path) as image:
                fmt = image.format
                if image.width * image.height > 40000000:
                    raise ValueError("La imagen supera el límite seguro de resolución.")
                image.verify()
        except OSError:
            raise ValueError("El contenido real no es una imagen válida.") from None
        return {"PNG": "image/png", "JPEG": "image/jpeg"}.get(
            fmt, "application/octet-stream"
        )
    if extension in {"docx", "xlsx"} and zipfile.is_zipfile(path):
        return "application/zip"
    if extension in {"doc", "xls"} and header.startswith(
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    ):
        return "application/x-ole-storage"
    return "application/octet-stream"


def local_object(key):
    import hashlib

    if os.getenv("WORKFLOW_DESKTOP") != "1":
        raise RuntimeError("El almacenamiento local exige modo escritorio explícito.")
    # Filename is never constructed from an untrusted path.
    return (
        Path(os.environ["DESKTOP_STORAGE_PATH"])
        / hashlib.sha256(key.encode()).hexdigest()
    )
