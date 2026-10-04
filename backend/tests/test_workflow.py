from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select


def move(client, proposal, action, **extra):
    response = client.post(
        f"/api/proposals/{proposal['id']}/transition",
        json={
            "action": action,
            "version": proposal["version"],
            "reason": "Integration justification",
            **extra,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_full_workflow_additional_information_only_once(
    case, login, actors, valid_documents
):
    manager, company, p, payload = case
    assert manager.post("/api/proposals", json=payload).status_code == 409
    assert (
        manager.post(
            f"/api/proposals/{p['id']}/transition",
            json={"action": "submit", "version": p["version"]},
        ).status_code
        == 409
    )
    valid_documents(p)
    assert (
        manager.post(
            f"/api/proposals/{p['id']}/report",
            json={
                "content": "Financial analysis and repayment capacity verified.",
                "final": True,
            },
        ).status_code
        == 200
    )
    p = move(manager, p, "submit")
    assert p["state"] == "in_analysis"
    supervisor = login("admin")
    response = supervisor.post(
        f"/api/proposals/{p['id']}/assign",
        json={
            "analyst_ids": [actors["analyst"]["id"]],
            "reason": "Specialist assignment",
        },
    )
    assert response.status_code == 200, response.text
    p = manager.get(f"/api/proposals/{p['id']}").json()
    analyst = login("analyst")
    p = move(
        analyst, p, "request_information", requirements=["Updated financial statement"]
    )
    assert p["state"] == "additional_requested"
    assert p["sla"]["risk"]["paused"]
    assert (
        manager.post(
            f"/api/proposals/{p['id']}/transition",
            json={"action": "resubmit", "version": p["version"]},
        ).status_code
        == 409
    )
    valid_documents(p)
    p = move(manager, p, "resubmit")
    assert p["state"] == "reanalysis"
    assert not p["sla"]["risk"]["paused"]
    assert (
        analyst.post(
            f"/api/proposals/{p['id']}/transition",
            json={
                "action": "request_information",
                "version": p["version"],
                "reason": "Again",
            },
        ).status_code
        == 409
    )
    p = move(analyst, p, "approve")
    assert p["state"] == "approved"
    assert p["sla"]["risk"]["ended_at"]
    assert manager.post("/api/proposals", json=payload).status_code in (200, 201)


def test_rejection_reopen_and_version_conflict(case, login, actors, valid_documents):
    manager, _, p, _ = case
    valid_documents(p)
    manager.post(
        f"/api/proposals/{p['id']}/report",
        json={"content": "Credit assessment.", "final": True},
    )
    stale = p["version"]
    p = move(manager, p, "submit")
    admin = login("admin")
    admin.post(
        f"/api/proposals/{p['id']}/assign",
        json={"analyst_ids": [actors["analyst"]["id"]], "reason": "Review case"},
    )
    p = manager.get(f"/api/proposals/{p['id']}").json()
    analyst = login("analyst")
    p = move(analyst, p, "reject")
    assert p["state"] == "rejected"
    assert (
        manager.post(
            f"/api/proposals/{p['id']}/transition",
            json={"action": "reopen", "version": stale, "reason": "Updated facts"},
        ).status_code
        == 409
    )
    p = move(manager, p, "reopen")
    assert (
        p["cycle"] == 2
        and p["extra_requests"] == 0
        and p["state"] == "documentation_pending"
    )


def test_idor_and_customer_redaction(case, login, actors):
    manager, company, p, _ = case
    other = login("other")
    for route in [f"/api/clients/{company['id']}", f"/api/proposals/{p['id']}"]:
        assert other.get(route).status_code == 404
    from app.db import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        db.get(User, actors["customer"]["id"]).client_id = company["id"]
        db.commit()
    customer = login("customer")
    detail = customer.get(f"/api/proposals/{p['id']}")
    assert detail.status_code == 200
    assert not {"report", "assignments", "observations", "participants"}.intersection(
        detail.json()
    )
    assert (
        customer.post(
            f"/api/proposals/{p['id']}/report",
            json={"content": "Unauthorized", "final": True},
        ).status_code
        == 403
    )
    assert customer.get("/api/admin/users").status_code == 403


def test_session_csrf_logout(case):
    client, company, p, _ = case
    assert client.get("/api/auth/me").status_code == 200
    csrf = client.headers.pop("X-CSRF-Token")
    assert (
        client.post(
            f"/api/proposals/{p['id']}/transition",
            json={"action": "cancel", "version": p["version"], "reason": "No csrf"},
        ).status_code
        == 403
    )
    client.headers["X-CSRF-Token"] = csrf
    assert (
        client.post(
            f"/api/proposals/{p['id']}/transition",
            headers={"Origin": "https://malicious.example"},
            json={
                "action": "cancel",
                "version": p["version"],
                "reason": "Cross origin",
            },
        ).status_code
        == 403
    )
    assert client.post("/api/auth/logout").status_code in (200, 204)
    assert client.get("/api/auth/me").status_code == 401


def test_report_export_binary_formats(case):
    client, _, p, _ = case
    response = client.post(
        f"/api/proposals/{p['id']}/report",
        json={"content": "Export assessment: credit risk.", "final": True},
    )
    assert response.status_code == 200
    for fmt, signature in [("pdf", b"%PDF"), ("docx", b"PK")]:
        response = client.get(f"/api/proposals/{p['id']}/report/export?format={fmt}")
        assert response.status_code == 200, response.text
        assert response.content.startswith(signature)


def test_auth_failure_idle_expiration_and_token_hash(login, actors):
    from datetime import timedelta
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db import SessionLocal
    from app.models import Session, now
    from app.security import digest

    anonymous = TestClient(app)
    assert (
        anonymous.post(
            "/api/auth/login",
            json={"email": actors["manager"]["email"], "password": "wrong"},
        ).status_code
        == 401
    )
    client = login("manager")
    raw = client.cookies["wf_session"]
    with SessionLocal() as db:
        session = db.scalar(select(Session).where(Session.token_hash == digest(raw)))
        assert session is not None and session.token_hash != raw
        session.last_seen = now() - timedelta(minutes=61)
        db.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_admin_rejects_customer_internal_roles_and_unknown_permissions(case, login):
    from uuid import uuid4

    _, company, _, _ = case
    admin = login("admin")
    roles = admin.get("/api/admin/roles").json()
    admin_role = next(r["id"] for r in roles if r["name"] == "ADMINISTRADOR")
    response = admin.post(
        "/api/admin/users",
        json={
            "email": uuid4().hex + "@example.com",
            "name": "Customer escalation",
            "password": "TestingSecure123!",
            "role_ids": [admin_role],
            "client_id": company["id"],
        },
    )
    assert response.status_code == 422
    response = admin.post(
        "/api/admin/roles",
        json={
            "name": "Invalid " + uuid4().hex,
            "permissions": ["arbitrary.superpower"],
        },
    )
    assert response.status_code == 422
    assert (
        login("manager")
        .post(
            "/api/admin/roles",
            json={"name": "Escalate", "permissions": ["user.manage"]},
        )
        .status_code
        == 403
    )


def test_locked_proposal_cannot_mutate_or_be_approved_by_manager(case, valid_documents):
    manager, _, p, payload = case
    invalid = dict(payload, amount="-1")
    assert manager.post("/api/proposals", json=invalid).status_code == 422
    valid_documents(p)
    manager.post(
        f"/api/proposals/{p['id']}/report",
        json={"content": "Completed analysis.", "final": True},
    )
    p = move(manager, p, "submit")
    assert (
        manager.patch(
            f"/api/proposals/{p['id']}",
            json={"version": p["version"], "amount": "200000"},
        ).status_code
        == 409
    )
    assert (
        manager.post(
            f"/api/proposals/{p['id']}/transition",
            json={
                "version": p["version"],
                "action": "approve",
                "reason": "Manager approval",
            },
        ).status_code
        == 403
    )


def test_concurrent_edits_preserve_single_version(case, login):
    manager, _, p, _ = case
    second = login("manager")

    def edit(client):
        return client.patch(
            f"/api/proposals/{p['id']}",
            json={"version": p["version"], "purpose": "Concurrent purpose"},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(edit, [manager, second]))
    assert sorted(codes) == [200, 409]
    versions = manager.get(f"/api/proposals/{p['id']}/versions").json()
    assert [v["version"] for v in versions] == [1, 2]


def test_analyst_cannot_read_other_proposals_same_company(
    case, login, actors, valid_documents
):
    manager, company, old, payload = case
    valid_documents(old)
    manager.post(
        f"/api/proposals/{old['id']}/report",
        json={"content": "Historical assessment.", "final": True},
    )
    old = move(manager, old, "submit")
    admin = login("admin")
    admin.post(
        f"/api/proposals/{old['id']}/assign",
        json={"analyst_ids": [actors["analyst"]["id"]], "reason": "First review"},
    )
    analyst = login("analyst")
    old = move(analyst, old, "reject")
    response = manager.post("/api/proposals", json=payload)
    assert response.status_code == 201
    current = response.json()
    valid_documents(current)
    manager.post(
        f"/api/proposals/{current['id']}/report",
        json={"content": "New assessment.", "final": True},
    )
    current = move(manager, current, "submit")
    # Remove the old assignment and assign only the new proposal. Historical scope must not leak.
    from app.db import SessionLocal
    from app.models import AnalystAssignment

    with SessionLocal() as db:
        for assignment in db.scalars(
            select(AnalystAssignment).where(AnalystAssignment.proposal_id == old["id"])
        ):
            assignment.active = False
        db.commit()
    admin.post(
        f"/api/proposals/{current['id']}/assign",
        json={"analyst_ids": [actors["analyst"]["id"]], "reason": "New case only"},
    )
    assert analyst.get(f"/api/proposals/{old['id']}").status_code == 404
    assert {p["id"] for p in analyst.get("/api/proposals").json()} == {current["id"]}
    history = analyst.get(f"/api/clients/{company['id']}").json()["proposals"]
    assert {p["id"] for p in history} == {current["id"]}
    search = analyst.get("/api/search", params={"q": old["code"]}).json()
    assert search["proposals"] == []


def test_customer_cannot_assign_despite_custom_internal_permissions(
    case, login, actors, valid_documents
):
    manager, company, p, _ = case
    valid_documents(p)
    manager.post(
        f"/api/proposals/{p['id']}/report",
        json={"content": "Ready for risk.", "final": True},
    )
    p = move(manager, p, "submit")
    from app.db import SessionLocal
    from app.models import User, Role

    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.name == "ADMINISTRADOR"))
        user = db.get(User, actors["customer"]["id"])
        user.client_id = company["id"]
        user.role_ids = [role.id]
        db.commit()
    customer = login("customer")
    assert (
        customer.post(
            f"/api/proposals/{p['id']}/assign",
            json={
                "analyst_ids": [actors["analyst"]["id"]],
                "reason": "Forbidden internal action",
            },
        ).status_code
        == 403
    )


def test_comment_id_must_belong_to_route_proposal(case):
    manager, _, old, payload = case
    response = manager.post(
        f"/api/proposals/{old['id']}/comments",
        json={"content": "Historical private comment"},
    )
    assert response.status_code == 201
    comment = response.json()
    move(manager, old, "cancel")
    response = manager.post("/api/proposals", json=payload)
    assert response.status_code == 201
    current = response.json()
    response = manager.patch(
        f"/api/proposals/{current['id']}/comments/{comment['id']}",
        json={"content": "Cross proposal tampering"},
    )
    assert response.status_code in (403, 404)


def test_private_information_requirement_hidden_from_customer(
    case, login, actors, valid_documents
):
    manager, company, p, _ = case
    valid_documents(p)
    manager.post(
        f"/api/proposals/{p['id']}/report",
        json={"content": "Risk assessment.", "final": True},
    )
    p = move(manager, p, "submit")
    admin = login("admin")
    admin.post(
        f"/api/proposals/{p['id']}/assign",
        json={"analyst_ids": [actors["analyst"]["id"]], "reason": "Risk review"},
    )
    analyst = login("analyst")
    p = move(
        analyst,
        p,
        "request_information",
        requirements=["Private diligence"],
        client_visible=False,
    )
    private = next(r for r in p["requirements"] if r["additional"])
    valid_documents(p)
    from app.db import SessionLocal
    from app.models import User, Document

    with SessionLocal() as db:
        user = db.get(User, actors["customer"]["id"])
        user.client_id = company["id"]
        document = db.scalar(
            select(Document).where(Document.requirement_id == private["id"])
        )
        document.name = "CONFIDENTIAL_" + p["id"] + ".pdf"
        did = document.id
        db.commit()
    customer = login("customer")
    detail = customer.get(f"/api/proposals/{p['id']}").json()
    assert private["id"] not in {r["id"] for r in detail["requirements"]}
    assert customer.get(f"/api/documents/{did}").status_code == 404
    assert customer.get(f"/api/documents/{did}/download-url").status_code == 404
    search = customer.get("/api/search", params={"q": "CONFIDENTIAL_" + p["id"]}).json()
    assert search["documents"] == []
