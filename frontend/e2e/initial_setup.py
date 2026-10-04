"""Real browser setup/login on an isolated database; no hosting claims."""

import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.request
from uuid import uuid4
from dotenv import dotenv_values
import psycopg
from sqlalchemy.engine import make_url
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]


def main():
    settings = dotenv_values(ROOT / ".env")
    base = make_url(settings["DATABASE_URL"])
    name = "workflow_browser_setup_" + uuid4().hex[:12] + "_test"
    administrator = base.set(
        drivername="postgresql", database="postgres"
    ).render_as_string(hide_password=False)
    children = []
    with psycopg.connect(administrator, autocommit=True) as db:
        db.execute(f'CREATE DATABASE "{name}"')
    env = os.environ.copy()
    token = secrets.token_urlsafe(48)
    env.update(
        {
            "DATABASE_URL": base.set(database=name).render_as_string(
                hide_password=False
            ),
            "SESSION_SECRET": secrets.token_urlsafe(48),
            "COOKIE_SECURE": "false",
            "APP_ENV": "test",
            "PUBLIC_ORIGIN": "http://127.0.0.1:3000",
            "WEB_SETUP_ENABLED": "true",
            "WEB_SETUP_TOKEN": token,
            "API_URL": "http://127.0.0.1:8001",
            "HOSTNAME": "127.0.0.1",
            "PORT": "3000",
        }
    )
    python = ROOT / ".venv/bin/python"
    # Match the real frontend Dockerfile's static asset copy.
    static = ROOT / "frontend/.next/standalone/.next/static"
    if not static.exists():
        static.symlink_to(ROOT / "frontend/.next/static", target_is_directory=True)
    try:
        for module in [("alembic", "upgrade", "head"), ("app.bootstrap",)]:
            subprocess.run(
                [str(python), "-m", *module],
                cwd=ROOT / "backend",
                env=env,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        children.append(
            subprocess.Popen(
                [
                    str(python),
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8001",
                    "--no-access-log",
                ],
                cwd=ROOT / "backend",
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )
        children.append(
            subprocess.Popen(
                ["node", ".next/standalone/server.js"],
                cwd=ROOT / "frontend",
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            assert all(child.poll() is None for child in children)
            try:
                with urllib.request.urlopen(
                    "http://127.0.0.1:3000/api/health", timeout=2
                ) as response:
                    if json.load(response)["status"] == "ok":
                        break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("Test web did not start")
        with urllib.request.urlopen(
            "http://127.0.0.1:3000/api/setup/status"
        ) as response:
            assert json.load(response) == {"required": True}
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path="/usr/bin/chromium", args=["--no-sandbox"]
            )
            page = browser.new_page(viewport={"width": 390, "height": 844})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto("http://127.0.0.1:3000/#setup=" + token)
            page.get_by_role("heading", name="Creá tu administrador").wait_for()
            assert page.evaluate("window.location.hash") == ""
            assert page.evaluate(
                "document.documentElement.scrollWidth <= window.innerWidth"
            )
            page.get_by_label("Tu nombre", exact=True).fill("Test administrator")
            page.get_by_label("Correo electrónico", exact=True).fill(
                "browser-setup@example.com"
            )
            page.get_by_label("Contraseña", exact=True).fill("TestingSecure123!")
            page.get_by_label("Repetir contraseña", exact=True).fill(
                "TestingSecure123!"
            )
            page.get_by_role("button", name="Crear administrador", exact=True).click()
            page.get_by_role("button", name="Iniciar sesión", exact=True).wait_for()
            assert not page.evaluate(
                "token => Object.values(localStorage).some(value => value.includes(token)) || Object.values(sessionStorage).some(value => value.includes(token))",
                token,
            )
            page.get_by_label("Correo electrónico", exact=True).fill(
                "browser-setup@example.com"
            )
            page.get_by_label("Contraseña", exact=True).fill("TestingSecure123!")
            page.get_by_role("button", name="Iniciar sesión", exact=True).click()
            page.get_by_role("heading", name="Tu operación, en perspectiva").wait_for()
            assert errors == [], errors
            page.screenshot(path="/tmp/workflow-web-setup.png")
            browser.close()
        print(
            "Web setup browser passed: first administrator, fragment removal, mobile layout, login and dashboard."
        )
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=15)
        assert name.startswith("workflow_browser_setup_") and name.endswith("_test")
        with psycopg.connect(administrator, autocommit=True) as db:
            db.execute(f'DROP DATABASE "{name}" WITH (FORCE)')


if __name__ == "__main__":
    main()
