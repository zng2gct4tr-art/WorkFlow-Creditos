from datetime import date
from pydantic import ValidationError
from fastapi import APIRouter, Depends, HTTPException, Request, Body
from sqlalchemy import select
from .db import get_db
from .models import *
from .security import (
    current_user,
    require,
    permissions,
    password_hash,
    user_dict,
    PERMISSIONS,
)
from .schemas import UserInput, RoleInput
from .domain import serial, client_access
from .audit import record

router = APIRouter(prefix="/api/admin", tags=["Administración"])
RESOURCES = {
    "users": User,
    "roles": Role,
    "products": Product,
    "profiles": Profile,
    "requirements": ChecklistRequirement,
    "holidays": Holiday,
    "settings": Setting,
    "permissions": Permission,
}


def authorize(db, u, resource):
    if u.client_id:
        raise HTTPException(403, "La administración es exclusiva de usuarios internos.")
    if resource not in RESOURCES:
        raise HTTPException(404, "Recurso de administración no encontrado.")
    require(
        db,
        u,
        "user.manage"
        if resource == "users"
        else "role.manage"
        if resource in {"roles", "permissions"}
        else "config.manage",
    )


def validate_roles(db, ids, client_id):
    if not ids or len(ids) != len(set(ids)):
        raise HTTPException(422, "Seleccione roles únicos.")
    roles = list(db.scalars(select(Role).where(Role.id.in_(ids))))
    if len(roles) != len(ids):
        raise HTTPException(422, "Rol no encontrado.")
    combined = {p for r in roles for p in r.permissions}
    client_perms = {
        "client.view",
        "document.upload",
        "document.download",
        "notification.view",
    }
    if client_id:
        if not db.get(Client, client_id):
            raise HTTPException(422, "Empresa no encontrada.")
        if combined - client_perms:
            raise HTTPException(
                422, "Un usuario cliente no puede tener permisos internos."
            )
    elif any(r.name == "CLIENTE" for r in roles):
        raise HTTPException(422, "El usuario cliente necesita una empresa vinculada.")


def values_for(db, resource, values, creating=True):
    if resource == "roles":
        try:
            body = RoleInput(**values)
        except ValidationError:
            raise HTTPException(422, "Revise el nombre y la lista de permisos.")
        if set(body.permissions) - set(PERMISSIONS):
            raise HTTPException(422, "Hay permisos desconocidos.")
        return body.model_dump()
    if resource in {"products", "profiles"}:
        allowed = {"name", "active"} | ({"rules"} if resource == "profiles" else set())
        if set(values) - allowed or (creating and not values.get("name")):
            raise HTTPException(422, "Revise el nombre y los campos configurables.")
        if "name" in values and not (2 <= len(str(values["name"])) <= 200):
            raise HTTPException(422, "El nombre debe tener entre 2 y 200 caracteres.")
        if "active" in values and not isinstance(values["active"], bool):
            raise HTTPException(422, "El estado activo debe ser verdadero o falso.")
        if "rules" in values and not isinstance(values["rules"], dict):
            raise HTTPException(422, "Las reglas deben ser un objeto.")
        return values
    if resource == "requirements":
        allowed = {
            "profile_id",
            "name",
            "category",
            "mandatory",
            "validity_days",
            "rules",
            "conditions",
            "active",
        }
        if set(values) - allowed or (creating and not values.get("name")):
            raise HTTPException(422, "Revise los campos del requisito documental.")
        if creating and not db.get(Profile, values.get("profile_id")):
            raise HTTPException(422, "Seleccione un perfil válido.")
        if "name" in values and not (2 <= len(str(values["name"])) <= 200):
            raise HTTPException(422, "Nombre de requisito inválido.")
        if "category" not in values and creating:
            values["category"] = "General"
        for key in ("mandatory", "active"):
            if key in values and not isinstance(values[key], bool):
                raise HTTPException(422, "Valor booleano inválido.")
        if values.get("validity_days") is not None and (
            not isinstance(values["validity_days"], int)
            or not 1 <= values["validity_days"] <= 36500
        ):
            raise HTTPException(422, "La vigencia debe ser un número positivo de días.")
        if "rules" in values:
            rules = values["rules"]
            if not isinstance(rules, dict) or set(rules) - {
                "required_fields",
                "min_confidence",
                "financial_year",
                "require_expiry",
            }:
                raise HTTPException(422, "Reglas documentales no soportadas.")
            if "required_fields" in rules and (
                not isinstance(rules["required_fields"], list)
                or any(
                    f
                    not in {
                        "rut",
                        "company_name",
                        "issue_date",
                        "expiry_date",
                        "dates",
                        "amounts",
                        "currencies",
                        "financial_years",
                        "signatures",
                    }
                    for f in rules["required_fields"]
                )
            ):
                raise HTTPException(422, "Campos de extracción no soportados.")
            if (
                "min_confidence" in rules
                and not 0 <= float(rules["min_confidence"]) <= 1
            ):
                raise HTTPException(422, "Confianza fuera de rango.")
        if "conditions" in values and (
            not isinstance(values["conditions"], dict)
            or set(values["conditions"])
            - {"min_amount", "max_amount", "products", "activities"}
        ):
            raise HTTPException(422, "Condiciones no soportadas.")
        return values
    if resource == "holidays":
        if set(values) - {"date", "name"} or not values.get("name"):
            raise HTTPException(422, "Indique fecha y nombre del feriado.")
        try:
            values["date"] = date.fromisoformat(values["date"])
        except (ValueError, KeyError, TypeError):
            raise HTTPException(422, "Fecha de feriado inválida.")
        return values
    if resource == "settings":
        if set(values) - {"key", "value"} or not isinstance(values.get("value"), dict):
            raise HTTPException(422, "Indique key y value como objeto.")
        key = values.get("key")
        v = values["value"]
        if key not in {"sla", "files", "rubric", "notifications"}:
            raise HTTPException(422, "Parámetro de configuración desconocido.")
        if key == "sla" and (
            set(v) != {"commercial", "risk"}
            or any(
                not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= 365
                for n in v.values()
            )
        ):
            raise HTTPException(
                422,
                "Los SLA deben incluir commercial y risk, entre 1 y 365 días hábiles.",
            )
        if key == "files":
            from .documents import MIMES

            if (
                set(v) != {"max_size_mb", "extensions"}
                or not isinstance(v.get("max_size_mb"), int)
                or not 1 <= v["max_size_mb"] <= 2048
                or not isinstance(v.get("extensions"), list)
                or not v["extensions"]
                or set(v["extensions"]) - set(MIMES)
            ):
                raise HTTPException(
                    422,
                    "Configure un límite técnico entre 1 y 2048 MB y formatos soportados.",
                )
        if key == "rubric" and (
            set(v)
            != {
                "completeness",
                "coherence",
                "analysis",
                "financial_consistency",
                "risk_identification",
                "clarity",
            }
            or not v
            or any(
                not isinstance(n, (int, float)) or n < 0 or n > 100 for n in v.values()
            )
            or sum(v.values()) != 100
        ):
            raise HTTPException(422, "Los pesos de la rúbrica deben sumar 100.")
        if key == "notifications" and (
            set(v) - {"email_enabled", "warning_days"}
            or not isinstance(v.get("email_enabled", False), bool)
        ):
            raise HTTPException(422, "Configuración de notificaciones inválida.")
        return values
    raise HTTPException(405, "Operación no disponible.")


@router.get("/{resource}")
def list_resource(resource: str, u=Depends(current_user), db=Depends(get_db)):
    authorize(db, u, resource)
    return [
        user_dict(db, v) if resource == "users" else serial(v)
        for v in db.scalars(select(RESOURCES[resource]).limit(1000))
    ]


@router.post("/{resource}", status_code=201)
def create(
    resource: str,
    request: Request,
    body: dict = Body(...),
    u=Depends(current_user),
    db=Depends(get_db),
):
    authorize(db, u, resource)
    if resource == "users":
        try:
            b = UserInput(**body)
        except ValidationError:
            raise HTTPException(422, "Revise email, nombre, contraseña y roles.")
        validate_roles(db, b.role_ids, b.client_id)
        if b.supervisor_id:
            supervisor = db.get(User, b.supervisor_id)
            if (
                not supervisor
                or supervisor.client_id
                or "team.view" not in permissions(db, supervisor)
            ):
                raise HTTPException(422, "Supervisor inválido.")
        vals = b.model_dump(exclude={"password"})
        vals["email"] = str(b.email).lower()
        obj = User(**vals, password_hash=password_hash(b.password))
    else:
        vals = values_for(db, resource, body)
        if resource == "settings" and db.get(Setting, vals["key"]):
            raise HTTPException(409, "El parámetro existe. Edítelo usando su clave.")
        obj = RESOURCES[resource](**vals)
    db.add(obj)
    db.flush()
    data = user_dict(db, obj) if resource == "users" else serial(obj)
    record(
        db,
        u,
        "admin.create",
        resource
        + ":"
        + str(getattr(obj, "id", getattr(obj, "key", getattr(obj, "date", "")))),
        after=data,
        request=request,
    )
    db.commit()
    return data


@router.put("/{resource}/{identifier}")
@router.patch("/{resource}/{identifier}")
def update(
    resource: str,
    identifier: str,
    request: Request,
    body: dict = Body(...),
    u=Depends(current_user),
    db=Depends(get_db),
):
    authorize(db, u, resource)
    key = date.fromisoformat(identifier) if resource == "holidays" else identifier
    obj = db.get(RESOURCES[resource], key)
    if not obj:
        raise HTTPException(404, "Registro no encontrado.")
    before = user_dict(db, obj) if resource == "users" else serial(obj)
    if resource == "users":
        if set(body) - {
            "name",
            "role_ids",
            "client_id",
            "active",
            "branch",
            "supervisor_id",
        }:
            raise HTTPException(422, "Campos de usuario no permitidos.")
        if obj.id == u.id and (body.get("active") is False or "role_ids" in body):
            raise HTTPException(
                409, "No puede quitarse su propio acceso administrativo."
            )
        client_id = body.get("client_id", obj.client_id)
        validate_roles(db, body.get("role_ids", obj.role_ids), client_id)
        if "active" in body and not isinstance(body["active"], bool):
            raise HTTPException(422, "Estado activo inválido.")
        if body.get("supervisor_id"):
            supervisor = db.get(User, body["supervisor_id"])
            if not supervisor or supervisor.id == obj.id or supervisor.client_id:
                raise HTTPException(422, "Supervisor inválido.")
        values = body
    else:
        values = values_for(
            db,
            resource,
            {"key": identifier, **body} if resource == "settings" else body,
            False,
        )
        if resource == "roles":
            for affected in db.scalars(select(User)):
                if (
                    obj.id in affected.role_ids
                    and affected.client_id
                    and set(values["permissions"])
                    - {
                        "client.view",
                        "document.upload",
                        "document.download",
                        "notification.view",
                    }
                ):
                    raise HTTPException(
                        409,
                        "Este rol está asignado a clientes; no puede conceder permisos internos.",
                    )
    for k, v in values.items():
        setattr(obj, k, v)
    data = user_dict(db, obj) if resource == "users" else serial(obj)
    record(
        db,
        u,
        "admin.update",
        resource + ":" + identifier,
        before=before,
        after=data,
        request=request,
    )
    db.commit()
    return data


@router.delete("/{resource}/{identifier}")
def remove(
    resource: str,
    identifier: str,
    request: Request,
    u=Depends(current_user),
    db=Depends(get_db),
):
    authorize(db, u, resource)
    obj = db.get(
        RESOURCES[resource],
        date.fromisoformat(identifier) if resource == "holidays" else identifier,
    )
    if not obj:
        raise HTTPException(404, "Registro no encontrado.")
    before = user_dict(db, obj) if resource == "users" else serial(obj)
    if resource == "users":
        if obj.id == u.id:
            raise HTTPException(409, "No puede desactivar su propio usuario.")
        obj.active = False
    elif resource in {"products", "profiles", "requirements"}:
        obj.active = False
    elif resource == "holidays":
        db.delete(obj)
    else:
        raise HTTPException(
            405,
            "La eliminación de roles y parámetros está restringida para preservar trazabilidad.",
        )
    record(
        db,
        u,
        "admin.deactivate",
        resource + ":" + identifier,
        before=before,
        request=request,
    )
    db.commit()
    return {"message": "Cambio registrado."}
