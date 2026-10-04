#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f .env ]]; then
  python3 - <<'PY'
from pathlib import Path
import secrets,base64
p=Path('.env')
s=Path('.env.example').read_text()
s=s.replace('replace-with-a-local-password',secrets.token_hex(24))
s=s.replace('replace-with-at-least-32-random-characters',secrets.token_hex(32))
s=s.replace('replace-with-a-local-object-storage-password',secrets.token_hex(24))
s=s.replace('replace-with-base64-encoded-64-random-bytes',base64.b64encode(secrets.token_bytes(64)).decode())
s=s.replace('replace-with-base64-encoded-32-random-bytes',base64.b64encode(secrets.token_bytes(32)).decode())
p.write_text(s);p.chmod(0o600)
PY
fi
docker compose config --quiet
docker compose up --build -d
printf '%s\n' 'Puerto local de la interfaz:'
docker compose port frontend 3000
printf '%s\n' 'API: http://localhost:8000/api/docs' 'Compruebe logs, estado del antivirus y una carga real antes de utilizar el flujo.'
