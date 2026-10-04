from sqlalchemy import select
from .db import SessionLocal
from .models import (
    Permission,
    Role,
    Product,
    Profile,
    ChecklistTemplate,
    ChecklistRequirement,
    Setting,
)
from .security import PERMISSIONS, ROLE_PERMISSIONS


def bootstrap():
    with SessionLocal() as db:
        for p in PERMISSIONS:
            if not db.get(Permission, p):
                db.add(Permission(name=p, description=p))
        for name, perms in ROLE_PERMISSIONS.items():
            existing = db.scalar(select(Role).where(Role.name == name))
            if not existing:
                db.add(Role(name=name, permissions=perms))
            elif name == "GESTOR COMERCIAL" and set(existing.permissions) == set(
                perms
            ) - {"document.validate"}:
                existing.permissions = perms
        for name in [
            "Préstamos empresariales",
            "Capital de trabajo",
            "Créditos a largo plazo",
            "Leasing",
            "Tarjetas de crédito",
            "Avales",
            "Cartas de crédito",
        ]:
            if not db.scalar(select(Product).where(Product.name == name)):
                db.add(Product(name=name))
        profiles = {
            "Empresas generales": [
                "Identificación y representación legal",
                "Estados financieros",
                "Declaración fiscal",
            ],
            "Productores agropecuarios primarios": [
                "Identificación y representación legal",
                "Estado patrimonial",
                "Plan de producción",
            ],
            "Desarrolladores inmobiliarios": [
                "Identificación y representación legal",
                "Estados financieros",
                "Presupuesto y permisos del proyecto",
            ],
        }
        for name, requirements in profiles.items():
            if not db.scalar(select(Profile).where(Profile.name == name)):
                p = Profile(name=name, rules={})
                db.add(p)
                db.flush()
                db.add(ChecklistTemplate(profile_id=p.id, name=name))
                for req in requirements:
                    db.add(
                        ChecklistRequirement(
                            profile_id=p.id,
                            name=req,
                            category="Identificación"
                            if "Identificación" in req
                            else "Financiero",
                            mandatory=True,
                            rules={"required_fields": ["rut", "company_name"]},
                            validity_days=365,
                        )
                    )
        defaults = {
            "sla": {"commercial": 7, "risk": 15},
            "files": {
                "max_size_mb": 100,
                "extensions": [
                    "pdf",
                    "jpg",
                    "jpeg",
                    "png",
                    "docx",
                    "xlsx",
                    "doc",
                    "xls",
                ],
            },
            "rubric": {
                "completeness": 20,
                "coherence": 20,
                "analysis": 20,
                "financial_consistency": 20,
                "risk_identification": 10,
                "clarity": 10,
            },
            "notifications": {"email_enabled": False, "warning_days": 1},
        }
        for key, value in defaults.items():
            if not db.get(Setting, key):
                db.add(Setting(key=key, value=value))
        db.commit()


if __name__ == "__main__":
    bootstrap()
