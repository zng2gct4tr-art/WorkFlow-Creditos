import argparse, os, getpass
from sqlalchemy import select
from .db import SessionLocal
from .models import User, Role
from .security import password_hash
from .audit import record

parser = argparse.ArgumentParser()
parser.add_argument("action", choices=["create-admin"])
parser.add_argument("email")
parser.add_argument("name")


def main():
    args = parser.parse_args()
    password = os.environ.get("BOOTSTRAP_PASSWORD") or getpass.getpass(
        "Contraseña inicial (12+ caracteres): "
    )
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == args.email.lower())):
            raise SystemExit("Usuario ya existente; no se modificó.")
        role = db.scalar(select(Role).where(Role.name == "ADMINISTRADOR"))
        if not role:
            raise SystemExit("Ejecute python -m app.bootstrap primero.")
        u = User(
            email=args.email.lower(),
            name=args.name,
            password_hash=password_hash(password),
            role_ids=[role.id],
        )
        db.add(u)
        db.flush()
        record(
            db,
            u,
            "user.bootstrap",
            u.id,
            after={"email": u.email, "role": "ADMINISTRADOR"},
        )
        db.commit()
    print(
        "Administrador creado. No se generaron clientes ni propuestas de demostración."
    )


if __name__ == "__main__":
    main()
