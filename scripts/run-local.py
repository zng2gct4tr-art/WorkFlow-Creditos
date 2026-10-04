#!/usr/bin/env python3
"""Run source-based development against private local services, without shell sourcing .env."""

import argparse, os, sys, subprocess
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument(
    "action", choices=["init", "api", "worker", "beat", "frontend", "admin", "test"]
)
parser.add_argument("args", nargs=argparse.REMAINDER)
opts = parser.parse_args()
config = {k: v for k, v in dotenv_values(ROOT / ".env").items() if v is not None}
config = {**config, **os.environ}
config.setdefault("API_URL", "http://127.0.0.1:8000")
python = str(ROOT / ".venv/bin/python")
if not Path(python).is_file():
    raise SystemExit("Create .venv and install backend/requirements.lock first.")
if opts.action == "init":
    for args in [
        ["-m", "alembic", "upgrade", "head"],
        ["-m", "app.bootstrap"],
        ["-m", "app.storage_init"],
    ]:
        subprocess.run([python, *args], cwd=ROOT / "backend", env=config, check=True)
    raise SystemExit(0)
commands = {
    "api": [
        python,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--reload",
        "--no-access-log",
    ],
    "worker": [
        python,
        "-m",
        "celery",
        "-A",
        "app.worker:celery_app",
        "worker",
        "--loglevel=info",
        "--concurrency=2",
    ],
    "beat": [
        python,
        "-m",
        "celery",
        "-A",
        "app.worker:celery_app",
        "beat",
        "--loglevel=info",
        "--schedule=/tmp/workflow-celerybeat",
    ],
    "admin": [python, "-m", "app.manage", "create-admin"],
    "test": [python, "-m", "pytest"],
    "frontend": ["npm", "run", "dev"],
}
os.chdir(ROOT / ("frontend" if opts.action == "frontend" else "backend"))
args = commands[opts.action] + opts.args
if opts.action == "frontend":
    os.execvpe(args[0], args, config)
else:
    os.execve(args[0], args, config)
