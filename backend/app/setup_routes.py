"""Opt-in, token-protected first-admin setup; never an unrestricted signup."""

import os
import secrets
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import EmailStr, Field
from sqlalchemy import select, text
from .db import get_db
from .models import User, Role
from .schemas import Input
from .security import password_hash, digest
from .auth_routes import check_origin, rate_limit
from .audit import record

router = APIRouter(prefix="/api/setup", tags=["Configuración inicial"])


class InitialAdmin(Input):
    email: EmailStr
    name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=12, max_length=128)


def setup_enabled():
    return (
        os.getenv("WEB_SETUP_ENABLED") == "true"
        and len(os.getenv("WEB_SETUP_TOKEN", "")) >= 32
    )


@router.get("/status")
def status(db=Depends(get_db)):
    enabled = setup_enabled()
    return {"required": bool(enabled and not db.scalar(select(User.id).limit(1)))}


@router.post("/admin", status_code=201)
def initial_admin(body: InitialAdmin, request: Request, db=Depends(get_db)):
    if not setup_enabled():
        raise HTTPException(404, "Configuración inicial no disponible.")
    check_origin(request)
    key = digest("setup:" + str(request.client.host if request.client else ""))
    rate_limit(db, key, 5)
    if not secrets.compare_digest(
        request.headers.get("X-Setup-Token", ""), os.environ["WEB_SETUP_TOKEN"]
    ):
        from .models import LoginAttempt

        db.add(LoginAttempt(key=key, success=False))
        db.commit()
        raise HTTPException(
            403,
            "El enlace de configuración no es válido. Abra el enlace privado de inicio.",
        )
    # Serialize first-admin creation, including concurrent requests.
    db.execute(text("SELECT pg_advisory_xact_lock(872124)"))
    if db.scalar(select(User.id).limit(1)):
        raise HTTPException(409, "La configuración inicial ya se completó.")
    role = db.scalar(select(Role).where(Role.name == "ADMINISTRADOR"))
    if not role:
        raise HTTPException(503, "El catálogo inicial todavía no está disponible.")
    user = User(
        email=body.email.lower(),
        name=body.name,
        password_hash=password_hash(body.password),
        role_ids=[role.id],
    )
    db.add(user)
    db.flush()
    record(
        db,
        user,
        "user.bootstrap",
        user.id,
        after={"email": user.email, "role": "ADMINISTRADOR"},
        request=request,
    )
    db.commit()
    return {"created": True}
