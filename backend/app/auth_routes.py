import os, secrets
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, func, text
from .db import get_db
from .models import User, Session, LoginAttempt, PasswordReset, now
from .security import (
    current_user,
    digest,
    verify_password,
    password_hash,
    user_dict,
    hasher,
)
from .schemas import Login, ResetRequest, ResetConfirm
from .audit import record

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))


def check_origin(request):
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in os.environ.get(
        "PUBLIC_ORIGIN", "http://localhost:3000"
    ).split(","):
        raise HTTPException(403, "Origen no permitido.")


def rate_limit(db, key, limit=10):
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(key[:14], 16)})
    count = db.scalar(
        select(func.count())
        .select_from(LoginAttempt)
        .where(
            LoginAttempt.key == key,
            LoginAttempt.created_at >= now() - timedelta(minutes=15),
            LoginAttempt.success.is_(False),
        )
    )
    if count >= limit:
        raise HTTPException(
            429, "Demasiados intentos. Espere 15 minutos antes de volver a intentar."
        )


@router.post("/login")
def login(body: Login, request: Request, response: Response, db=Depends(get_db)):
    check_origin(request)
    ip = request.client.host if request.client else ""
    keys = [digest("email:" + body.email.lower()), digest("ip:" + ip)]
    for key in sorted(keys):
        rate_limit(db, key, 10 if key == keys[0] else 50)
    u = db.scalar(select(User).where(User.email == body.email.lower()))
    valid = verify_password(u.password_hash if u else DUMMY_HASH, body.password)
    for key in keys:
        db.add(LoginAttempt(key=key, success=bool(u and u.active and valid)))
    if not u or not u.active or not valid:
        record(
            db,
            None,
            "auth.login_failed",
            "auth",
            after={"identity_hash": keys[0]},
            request=request,
        )
        db.commit()
        raise HTTPException(401, "Email o contraseña incorrectos.")
    token = secrets.token_urlsafe(48)
    csrf = secrets.token_urlsafe(32)
    s = Session(
        token_hash=digest(token),
        user_id=u.id,
        csrf=csrf,
        expires_at=now() + timedelta(hours=12),
    )
    db.add(s)
    db.flush()
    request.state.session_id = s.id
    record(db, u, "auth.login", u.id, request=request)
    db.commit()
    secure = os.environ.get("COOKIE_SECURE", "true").lower() == "true"
    response.set_cookie(
        "wf_session",
        token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=43200,
        path="/",
    )
    response.set_cookie(
        "wf_csrf",
        csrf,
        httponly=False,
        secure=secure,
        samesite="strict",
        max_age=43200,
        path="/",
    )
    return {"user": user_dict(db, u), "csrf_token": csrf}


@router.get("/me")
def me(u=Depends(current_user), db=Depends(get_db)):
    return user_dict(db, u)


@router.post("/logout")
def logout(
    request: Request, response: Response, u=Depends(current_user), db=Depends(get_db)
):
    s = db.get(Session, request.state.session_id)
    db.delete(s)
    record(db, u, "auth.logout", u.id, request=request)
    db.commit()
    response.delete_cookie("wf_session")
    response.delete_cookie("wf_csrf")
    return {"message": "Sesión cerrada."}


@router.post("/password/reset-request")
def reset_request(body: ResetRequest, request: Request, db=Depends(get_db)):
    check_origin(request)
    key = digest("reset:" + str(request.client.host if request.client else ""))
    rate_limit(db, key, 5)
    db.add(LoginAttempt(key=key, success=False))
    u = db.scalar(
        select(User).where(User.email == body.email.lower(), User.active.is_(True))
    )
    if os.getenv("WORKFLOW_DESKTOP") == "1" and not os.getenv("SMTP_HOST"):
        raise HTTPException(
            503,
            "El correo externo no está configurado. Solicite al administrador el cambio de contraseña.",
        )
    if u:
        token = secrets.token_urlsafe(48)
        reset = PasswordReset(
            user_id=u.id,
            token_hash=digest(token),
            expires_at=now() + timedelta(minutes=30),
        )
        db.add(reset)
        record(db, u, "auth.reset_requested", u.id, request=request)
        # Dispatch ephemeral token only through the configured SMTP channel, never in logs or response.
        from .worker import send_password_reset

        try:
            send_password_reset.delay(u.id, token)
        except Exception:
            db.rollback()
            raise HTTPException(
                503,
                "La recuperación no está disponible temporalmente. Contacte al administrador.",
            )
    db.commit()
    return {
        "message": "Si el correo está registrado recibirá instrucciones para recuperar su acceso."
    }


@router.post("/password/reset-confirm")
def reset_confirm(body: ResetConfirm, request: Request, db=Depends(get_db)):
    check_origin(request)
    r = db.scalar(
        select(PasswordReset)
        .where(PasswordReset.token_hash == digest(body.token))
        .with_for_update()
    )
    if not r or r.used or r.expires_at < now():
        raise HTTPException(400, "El enlace de recuperación venció o ya fue utilizado.")
    u = db.get(User, r.user_id)
    u.password_hash = password_hash(body.password)
    r.used = True
    for s in db.scalars(select(Session).where(Session.user_id == u.id)):
        db.delete(s)
    record(db, u, "auth.password_changed", u.id, request=request)
    db.commit()
    return {"message": "Contraseña actualizada. Inicie sesión nuevamente."}
