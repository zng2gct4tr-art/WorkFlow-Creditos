#!/usr/bin/env python3
"""Start the actual stack in Codespaces and prepare a private browser link.

No accounts, payment methods, machine upgrades or keepalive requests are created.
Generated secrets and documents must never be committed or printed.
"""

import base64
from pathlib import Path
import os
import secrets
import subprocess
import time
import urllib.request
import json
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def parse_settings(path):
    # Values generated here contain no shell syntax. Never source .env as code.
    values = {}
    for line in path.read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            if key.strip().isalnum() or key.strip().replace("_", "").isalnum():
                values[key.strip()] = value.strip()
    return values


def prepare(root, name, forwarding_domain):
    # The link is constructed only from validated Codespaces-provided host parts.
    import re

    if not re.fullmatch(r"[a-z0-9-]+", name) or not re.fullmatch(
        r"[a-z0-9.-]+", forwarding_domain
    ):
        raise RuntimeError("Invalid Codespaces host")
    directory = root / ".workflow"
    directory.mkdir(mode=0o700, exist_ok=True)
    for service in ("postgres", "redis", "objects", "antivirus"):
        (directory / "data" / service).mkdir(parents=True, exist_ok=True)
    settings_file = root / ".env"
    settings = parse_settings(settings_file) if settings_file.exists() else {}
    # Preserve every existing key and password; never silently change databases.
    if not settings_file.exists():
        settings = parse_settings(root / ".env.example")
        settings.update(
            {
                "POSTGRES_PASSWORD": secrets.token_hex(24),
                "SESSION_SECRET": secrets.token_hex(32),
                "AZURE_STORAGE_ACCOUNT_KEY": base64.b64encode(
                    secrets.token_bytes(64)
                ).decode(),
                "STORAGE_ENCRYPTION_KEY": base64.b64encode(
                    secrets.token_bytes(32)
                ).decode(),
            }
        )
    token = settings.get("WEB_SETUP_TOKEN") or secrets.token_urlsafe(48)
    if len(token) < 32:
        raise RuntimeError("Existing setup token is invalid; refusing to replace it.")
    origin = f"https://{name}-3000.{forwarding_domain}"
    settings.update(
        {
            "FRONTEND_PORT": "3000",
            "PUBLIC_ORIGIN": origin,
            "COOKIE_SECURE": "true",
            "WEB_SETUP_ENABLED": "true",
            "WEB_SETUP_TOKEN": token,
            "APP_ENV": "codespaces",
            "AI_PROVIDER": "local",
            "OCR_PROVIDER": "local",
        }
    )
    password = settings["POSTGRES_PASSWORD"]
    settings["DATABASE_URL"] = (
        f"postgresql+psycopg://workflow:{password}@localhost:5432/workflow"
    )
    account = settings["AZURE_STORAGE_ACCOUNT_KEY"]
    settings["AZURE_STORAGE_CONNECTION_STRING"] = (
        f"DefaultEndpointsProtocol=http;AccountName=workflow;AccountKey={account};BlobEndpoint=http://127.0.0.1:10000/workflow;"
    )
    # The standard remote environment must use the official Azurite image, not
    # an image name that exists only in a different onboarding machine.
    settings.pop("AZURITE_IMAGE", None)
    if any("\n" in value or "\r" in value for value in settings.values()):
        raise RuntimeError("Invalid multiline setting")
    fd, name = tempfile.mkstemp(prefix=".workflow-settings-", dir=root)
    try:
        with os.fdopen(fd, "w") as target:
            for key, value in settings.items():
                target.write(f"{key}={value}\n")
        os.replace(name, settings_file)
    finally:
        Path(name).unlink(missing_ok=True)
    os.chmod(settings_file, 0o600)
    guide = directory / "ABRIR-WEB.md"
    guide.write_text(
        "# Abrir WorkFlow Créditos\n\n"
        f"[**Abrir la aplicación web**]({origin}/#setup={token})\n\n"
        "Abrí la vista previa de este archivo con Ctrl+Shift+V y hacé clic en el enlace. "
        "La primera vez elegí tu nombre, email y contraseña de administrador; después iniciá sesión.\n\n"
        "Este archivo contiene un enlace privado de configuración: no lo compartas. "
        "Luego de crear el administrador, el enlace normal de la web no necesita esa clave.\n\n"
        "Mantené el puerto privado durante la configuración. No agregues una tarjeta ni actives uso pago. "
        "Detené el Codespace al terminar. Sin medio de pago, agotar la cuota bloquea el uso. "
        "No borres ni reconstruyas el entorno sin respaldar datos y claves.\n",
        encoding="utf-8",
    )
    os.chmod(guide, 0o600)
    return origin


def main():
    if os.getenv("CODESPACES") != "true":
        raise SystemExit("This startup is exclusively for GitHub Codespaces.")
    prepare(
        ROOT,
        os.environ["CODESPACE_NAME"],
        os.environ.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "app.github.dev"),
    )
    compose = [
        "docker",
        "compose",
        "-f",
        "docker-compose.yml",
        "-f",
        "docker-compose.codespaces.yml",
    ]
    subprocess.run(compose + ["config", "--quiet"], cwd=ROOT, check=True)
    subprocess.run(compose + ["up", "--build", "-d"], cwd=ROOT, check=True)
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:8000/api/ready", timeout=5
            ) as response:
                if json.load(response).get("status") == "ok":
                    with urllib.request.urlopen(
                        "http://127.0.0.1:3000/api/health", timeout=5
                    ) as frontend:
                        if json.load(frontend).get("status") == "ok":
                            print(
                                "Web ready. Open .workflow/ABRIR-WEB.md in Markdown preview to access your private setup link."
                            )
                            return
        except Exception:
            pass
        time.sleep(3)
    raise SystemExit(
        "Services not ready. Review startup logs; no data or volumes were deleted. Do not bypass antivirus."
    )


if __name__ == "__main__":
    main()
