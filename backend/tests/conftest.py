"""PostgreSQL integration fixtures. No production DB or external service mocks here."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from dotenv import dotenv_values

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ROOT = BACKEND_ROOT.parent
settings = dotenv_values(ROOT / ".env")
url = make_url(
    os.getenv("TEST_DATABASE_URL")
    or os.getenv("DATABASE_URL")
    or settings.get(
        "DATABASE_URL", "postgresql+psycopg://workflow:workflow@localhost:5432/workflow"
    )
)
if not url.database.endswith("_test"):
    url = url.set(database=url.database + "_test")
os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
os.environ["COOKIE_SECURE"] = "false"


@pytest.fixture(scope="session", autouse=True)
def database():
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.exec_driver_sql(
            "SELECT 1 FROM pg_database WHERE datname = %s", (url.database,)
        ).scalar()
        if not exists:
            if not url.database.replace("_", "").isalnum():
                raise ValueError("Unsafe test database name")
            conn.exec_driver_sql(f'CREATE DATABASE "{url.database}"')
    admin.dispose()
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        check=True,
    )
    from app.bootstrap import bootstrap

    bootstrap()


@pytest.fixture
def actors(database):
    from app.db import SessionLocal
    from app.models import User, Role
    from app.security import password_hash

    result = {}
    with SessionLocal() as db:
        encoded = password_hash("TestingSecure123!")
        for key, role in [
            ("manager", "GESTOR COMERCIAL"),
            ("other", "GESTOR COMERCIAL"),
            ("analyst", "ANALISTA"),
            ("supervisor", "SUPERVISOR"),
            ("admin", "ADMINISTRADOR"),
            ("customer", "CLIENTE"),
        ]:
            r = db.scalar(select(Role).where(Role.name == role))
            user = User(
                email=f"{key}-{uuid4().hex}@example.com",
                name=f"Test {key}",
                password_hash=encoded,
                role_ids=[r.id],
            )
            db.add(user)
            db.flush()
            result[key] = {"id": user.id, "email": user.email}
        db.commit()
    return result


@pytest.fixture
def login(actors):
    from fastapi.testclient import TestClient
    from app.main import app

    clients = []

    def make(role):
        client = TestClient(app, base_url="http://localhost")
        response = client.post(
            "/api/auth/login",
            json={"email": actors[role]["email"], "password": "TestingSecure123!"},
        )
        assert response.status_code == 200, response.text
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.close()


@pytest.fixture
def case(login, actors):
    manager = login("manager")
    catalog = manager.get("/api/catalog").json()
    token = str(uuid4().int)
    response = manager.post(
        "/api/clients",
        json={
            "name": "Integration Company",
            "rut": token[:12],
            "account_number": token,
            "manager_id": actors["manager"]["id"],
            "profile_id": catalog["profiles"][0]["id"],
        },
    )
    assert response.status_code in (200, 201), response.text
    client = response.json()
    payload = {
        "client_id": client["id"],
        "product_id": catalog["products"][0]["id"],
        "amount": "100000.25",
        "currency": "UYU",
        "term_months": 12,
        "purpose": "Working capital",
    }
    response = manager.post("/api/proposals", json=payload)
    assert response.status_code in (200, 201), response.text
    return manager, client, response.json(), payload


@pytest.fixture
def valid_documents(actors):
    """Direct DB document fixture isolates workflow from antivirus/storage/OCR services."""

    def fill(proposal):
        from app.db import SessionLocal
        from app.models import Document

        with SessionLocal() as db:
            for requirement in proposal["requirements"]:
                if not requirement.get("documents"):
                    db.add(
                        Document(
                            requirement_id=requirement["id"],
                            uploader_id=actors["manager"]["id"],
                            name="verified.pdf",
                            storage_key="tests/" + uuid4().hex,
                            sha256="a" * 64,
                            mime="application/pdf",
                            size=50,
                            status="correct",
                            extraction={"rut": "123456789012"},
                        )
                    )
            db.commit()

    return fill
