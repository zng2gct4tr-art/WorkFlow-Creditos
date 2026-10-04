"""First-admin setup against a separate disposable PostgreSQL database."""

import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def setup_client(database, monkeypatch):
    from app.main import app
    from app.db import get_db
    from app import bootstrap
    from fastapi.testclient import TestClient

    name = "workflow_setup_" + uuid4().hex + "_test"
    base = make_url(os.environ["DATABASE_URL"])
    administrator = create_engine(
        base.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    with administrator.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = create_engine(base.set(database=name))
    factory = sessionmaker(engine, expire_on_commit=False)
    old = app.dependency_overrides.get(get_db)

    def dependency():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = dependency
    try:
        env = os.environ.copy()
        env["DATABASE_URL"] = base.set(database=name).render_as_string(
            hide_password=False
        )
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            env=env,
            cwd=Path(__file__).resolve().parents[1],
            check=True,
            capture_output=True,
        )
        monkeypatch.setattr(bootstrap, "SessionLocal", factory)
        bootstrap.bootstrap()
        monkeypatch.setenv("WEB_SETUP_ENABLED", "true")
        monkeypatch.setenv("WEB_SETUP_TOKEN", "test-setup-token-" + "a" * 40)
        monkeypatch.setenv("PUBLIC_ORIGIN", "https://example.app.github.dev")
        with TestClient(app, base_url="https://example.app.github.dev") as client:
            yield client, factory, app
    finally:
        if old is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = old
        engine.dispose()
        assert name.startswith("workflow_setup_") and name.endswith("_test")
        with administrator.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
        administrator.dispose()


def payload(email="first-admin@example.com"):
    return {
        "email": email,
        "name": "Initial administrator",
        "password": "TestingSecure123!",
    }


def setup_headers():
    return {
        "X-Setup-Token": os.environ["WEB_SETUP_TOKEN"],
        "Origin": "https://example.app.github.dev",
    }


def test_setup_requires_opt_in_token_and_allowed_origin(setup_client, monkeypatch):
    client, factory, _ = setup_client
    monkeypatch.setenv("WEB_SETUP_ENABLED", "false")
    assert client.get("/api/setup/status").json() == {"required": False}
    assert (
        client.post(
            "/api/setup/admin", json=payload(), headers=setup_headers()
        ).status_code
        == 404
    )
    monkeypatch.setenv("WEB_SETUP_ENABLED", "true")
    assert client.get("/api/setup/status").json() == {"required": True}
    headers = setup_headers() | {"X-Setup-Token": "invalid"}
    assert (
        client.post("/api/setup/admin", json=payload(), headers=headers).status_code
        == 403
    )
    headers = setup_headers() | {"Origin": "https://attacker.example"}
    assert (
        client.post("/api/setup/admin", json=payload(), headers=headers).status_code
        == 403
    )
    from app.models import User

    with factory() as db:
        assert list(db.scalars(select(User))) == []


def test_first_admin_once_real_login_and_audit_without_token(setup_client):
    client, factory, _ = setup_client
    token = os.environ["WEB_SETUP_TOKEN"]
    response = client.post("/api/setup/admin", json=payload(), headers=setup_headers())
    assert response.status_code == 201
    assert client.get("/api/setup/status").json() == {"required": False}
    assert (
        client.post(
            "/api/setup/admin",
            json=payload("second@example.com"),
            headers=setup_headers(),
        ).status_code
        == 409
    )
    login = client.post(
        "/api/auth/login",
        json={"email": payload()["email"], "password": payload()["password"]},
        headers={"Origin": "https://example.app.github.dev"},
    )
    assert (
        login.status_code == 200
        and "user.manage" in login.json()["user"]["permissions"]
    )
    from app.models import AuditEvent, User

    with factory() as db:
        assert len(list(db.scalars(select(User)))) == 1
        events = list(db.scalars(select(AuditEvent)))
        assert any(event.action == "user.bootstrap" for event in events)
        assert all(
            token not in str(event.__dict__)
            and payload()["password"] not in str(event.__dict__)
            for event in events
        )


def test_concurrent_first_admin_allows_only_one(setup_client):
    _, factory, app = setup_client
    from fastapi.testclient import TestClient

    headers = setup_headers()

    def create(index):
        with TestClient(app, base_url="https://example.app.github.dev") as client:
            return client.post(
                "/api/setup/admin",
                json=payload(f"admin{index}@example.com"),
                headers=headers,
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(create, range(2)))
    assert sorted(statuses) == [201, 409]
    from app.models import User

    with factory() as db:
        assert len(list(db.scalars(select(User)))) == 1
