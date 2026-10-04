import logging, os, time, uuid
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from .db import engine, get_db
from .security import current_user
from . import (
    auth_routes,
    client_routes,
    proposal_routes,
    document_routes,
    admin_routes,
    report_routes,
    setup_routes,
)

if os.getenv("APP_ENV") == "production":
    if (
        len(os.getenv("SESSION_SECRET", "")) < 32
        or os.getenv("COOKIE_SECURE", "true").lower() != "true"
        or not os.getenv("PUBLIC_ORIGIN", "").startswith("https://")
    ):
        raise RuntimeError(
            "Production requires SESSION_SECRET, HTTPS PUBLIC_ORIGIN and secure cookies."
        )

app = FastAPI(
    title="WorkFlow Créditos",
    version="1.0.0",
    description="Gestión empresarial de crédito con autorización por cartera y trazabilidad.",
    docs_url="/api/docs"
    if os.getenv("APP_ENV", "development") != "production"
    else None,
    openapi_url="/api/openapi.json"
    if os.getenv("APP_ENV", "development") != "production"
    else None,
)
for router in [
    auth_routes.router,
    client_routes.router,
    proposal_routes.router,
    document_routes.router,
    admin_routes.router,
    report_routes.router,
    setup_routes.router,
]:
    app.include_router(router)
from .observability import configure, requests

configure()
logger = logging.getLogger("workflow.http")


@app.middleware("http")
async def headers(request: Request, call_next):
    request_id = str(uuid.uuid4())
    started = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        logger.error("request_failed", extra={"request_id": request_id})
        response = JSONResponse(
            status_code=500,
            content={
                "detail": "No se pudo completar la operación. Intente nuevamente.",
                "request_id": request_id,
            },
        )
    response.headers.update(
        {
            "X-Request-ID": request_id,
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "same-origin",
            "Cache-Control": "no-store",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        }
    )
    if os.environ.get("APP_ENV") == "production":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    requests[response.status_code] += 1
    logger.info(
        "request_completed",
        extra={
            "request_id": request_id,
            "status": response.status_code,
            "duration_ms": round((time.monotonic() - started) * 1000),
        },
    )
    return response


@app.exception_handler(IntegrityError)
async def integrity(request, exc):
    return JSONResponse(
        status_code=409,
        content={
            "detail": "La operación entra en conflicto con un registro existente. Revise RUT, cuenta, email o propuesta activa."
        },
    )


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "workflow-api"}


@app.get("/api/ready")
def ready():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        from .documents import storage_available
        import redis, socket

        dependencies = {"database": "connected"}
        try:
            if os.getenv("WORKFLOW_DESKTOP") == "1":
                from .worker import celery_app

                if not celery_app.available():
                    raise RuntimeError("Desktop worker unavailable")
            else:
                redis.Redis.from_url(
                    os.getenv("REDIS_URL", "redis://localhost:6379/0"),
                    socket_connect_timeout=3,
                    socket_timeout=3,
                ).ping()
            dependencies["queue"] = "connected"
        except Exception:
            dependencies["queue"] = "unavailable"
        try:
            if os.getenv("WORKFLOW_DESKTOP") == "1":
                from .desktop_services import defender_available

                defender_available()
            else:
                with socket.create_connection(
                    (
                        os.getenv("CLAMAV_HOST", "clamav"),
                        int(os.getenv("CLAMAV_PORT", "3310")),
                    ),
                    timeout=3,
                ) as scanner:
                    scanner.sendall(b"zPING\0")
                    scanner.settimeout(3)
                    if b"PONG" not in scanner.recv(1024):
                        raise RuntimeError()
            dependencies["antimalware"] = "connected"
        except Exception:
            dependencies["antimalware"] = "unavailable"
        try:
            storage_available()
            dependencies["storage"] = "connected"
        except Exception:
            dependencies["storage"] = "unavailable"
        good = all(v == "connected" for v in dependencies.values())
        return JSONResponse(
            status_code=200 if good else 503,
            content={
                "status": "ok" if good else "unavailable",
                "dependencies": dependencies,
            },
        )
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "database": "disconnected"},
        )


@app.get("/api/metrics")
def metrics(
    request: Request,
    db=Depends(get_db),
    u=Depends(current_user),
):
    from .security import require
    from fastapi import HTTPException
    from fastapi.responses import Response

    if u.client_id:
        raise HTTPException(403, "Métricas internas.")
    require(db, u, "config.manage")
    lines = ["# TYPE workflow_http_requests_total counter"] + [
        f'workflow_http_requests_total{{status="{status}"}} {count}'
        for status, count in sorted(requests.items())
    ]
    return Response("\n".join(lines) + "\n", media_type="text/plain")
