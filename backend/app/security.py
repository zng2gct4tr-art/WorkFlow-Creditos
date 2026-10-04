import hashlib, hmac, os, secrets
from datetime import timedelta
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from .db import get_db
from .models import User, Role, Session, now

hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
PERMISSIONS = [
    "client.view",
    "client.create",
    "client.edit",
    "client.import",
    "portfolio.all",
    "team.view",
    "proposal.create",
    "proposal.edit",
    "proposal.submit",
    "proposal.cancel",
    "proposal.reopen",
    "document.upload",
    "document.download",
    "document.validate",
    "risk.view",
    "risk.approve",
    "risk.reject",
    "risk.request",
    "assignment.manage",
    "report.view",
    "report.export",
    "report.assess",
    "audit.view",
    "audit.export",
    "comment.write",
    "user.manage",
    "role.manage",
    "config.manage",
    "notification.view",
]
ROLE_PERMISSIONS = {
    "CLIENTE": [
        "client.view",
        "document.upload",
        "document.download",
        "notification.view",
    ],
    "GESTOR COMERCIAL": [
        "client.view",
        "client.create",
        "client.edit",
        "client.import",
        "proposal.create",
        "proposal.edit",
        "proposal.submit",
        "proposal.cancel",
        "proposal.reopen",
        "document.upload",
        "document.download",
        "document.validate",
        "comment.write",
        "notification.view",
        "report.view",
        "report.export",
    ],
    "ANALISTA": [
        "client.view",
        "risk.view",
        "document.download",
        "document.validate",
        "risk.approve",
        "risk.reject",
        "risk.request",
        "comment.write",
        "notification.view",
        "report.view",
        "report.export",
        "report.assess",
    ],
    "SUPERVISOR": [
        "client.view",
        "team.view",
        "risk.view",
        "document.download",
        "document.validate",
        "assignment.manage",
        "proposal.reopen",
        "comment.write",
        "notification.view",
        "report.view",
        "report.export",
        "report.assess",
    ],
    "ADMINISTRADOR": PERMISSIONS,
    "AUDITOR": [
        "client.view",
        "portfolio.all",
        "risk.view",
        "document.download",
        "report.view",
        "report.export",
        "audit.view",
        "audit.export",
        "notification.view",
    ],
}


def password_hash(password):
    if (
        len(password) < 12
        or len(password) > 128
        or not any(c.isupper() for c in password)
        or not any(c.islower() for c in password)
        or not any(c.isdigit() for c in password)
    ):
        raise HTTPException(
            422,
            "La contraseña debe tener entre 12 y 128 caracteres e incluir mayúsculas, minúsculas y números.",
        )
    return hasher.hash(password)


def verify_password(encoded, password):
    try:
        return hasher.verify(encoded, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def digest(value):
    secret = os.environ.get(
        "SESSION_SECRET", "development-only-session-pepper-change-before-production"
    )
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def permissions(db, user):
    if not user.role_ids:
        return set()
    return {
        p
        for r in db.scalars(select(Role).where(Role.id.in_(user.role_ids)))
        for p in r.permissions
    }


def require(db, user, p):
    if p not in permissions(db, user):
        raise HTTPException(403, "No tiene permiso para realizar esta acción.")


def current_user(request: Request, db=Depends(get_db)):
    token = request.cookies.get("wf_session", "")
    session = (
        db.scalar(select(Session).where(Session.token_hash == digest(token)))
        if token
        else None
    )
    if (
        not session
        or session.expires_at <= now()
        or session.last_seen + timedelta(minutes=60) <= now()
    ):
        raise HTTPException(401, "La sesión ha vencido. Inicie sesión nuevamente.")
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, "Usuario no disponible.")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf = request.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(session.csrf, csrf):
            raise HTTPException(
                403, "La solicitud no pudo verificarse. Actualice la página."
            )
        origin = request.headers.get("origin")
        allowed = os.environ.get("PUBLIC_ORIGIN", "http://localhost:3000").split(",")
        if origin and origin.rstrip("/") not in allowed:
            raise HTTPException(403, "Origen no permitido.")
    session.last_seen = now()
    db.commit()
    request.state.session_id = session.id
    request.state.user = user
    return user


def user_dict(db, u):
    return dict(
        id=u.id,
        name=u.name,
        email=u.email,
        client_id=u.client_id,
        permissions=sorted(permissions(db, u)),
        role_ids=u.role_ids,
        active=u.active,
        branch=u.branch,
        supervisor_id=u.supervisor_id,
    )
