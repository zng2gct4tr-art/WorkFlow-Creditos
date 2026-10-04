# WorkFlow Créditos

Base funcional para gestionar expedientes de crédito, documentos y revisión humana, con API FastAPI, interfaz Next.js y procesamiento asíncrono. El repositorio contiene una implementación inicial: requiere validación funcional, de seguridad y normativa antes de utilizar datos bancarios reales.

## Inicio local

Requisitos: Docker Engine con Compose v2.24 o superior, recursos suficientes para PostgreSQL, Redis, Azurite, Mailpit, ClamAV, API, worker e interfaz. ClamAV descarga sus firmas y puede tardar varios minutos en estar disponible.

Inicio automático: `./scripts/dev-up.sh` genera `.env` con secretos locales si falta y arranca Compose. Conserva cualquier `.env` existente.

Como alternativa manual:

```bash
cp .env.example .env
# Editar .env: contraseñas independientes y SESSION_SECRET aleatorio.
# Generar claves base64 independientes: 64 bytes para Azure y 32 para AES-GCM.
# scripts/dev-up.sh ya genera ambos valores y connection string.
docker compose up --build -d
docker compose logs -f backend worker
```

Interfaz: http://localhost:3000 (o el puerto local de `FRONTEND_PORT`, ajustando `PUBLIC_ORIGIN`). API y OpenAPI: http://localhost:8000/api/docs. Correo local Mailpit: http://localhost:8025. Azurite escucha en localhost:10000. Los puertos publicados solo escuchan en la interfaz local. PostgreSQL, Redis, Blob y antivirus también se exponen exclusivamente en localhost para pruebas desde el host.

Las migraciones y el catálogo inicial se ejecutan al iniciar la API. No se crean clientes ni expedientes ficticios. Crear el primer administrador con el comando soportado por el backend, proporcionando una contraseña segura temporalmente:

```bash
docker compose exec backend python -m app.manage create-admin admin@example.com 'Administrador'
```

Si el comando utiliza `BOOTSTRAP_PASSWORD`, configurarla temporalmente en `.env`, recrear el backend y retirarla después de crear el usuario. No almacenar contraseñas en el historial del shell. Consulte `python -m app.manage --help` para la sintaxis de esta versión.

```bash
docker compose down
# docker compose down -v elimina permanentemente los datos locales.
```

## Desarrollo y comprobación

```bash
# Desde la raíz, con .env y servicios locales configurados:
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r backend/requirements.lock
.venv/bin/python scripts/run-local.py init
.venv/bin/python scripts/run-local.py test
# En terminales separadas:
.venv/bin/python scripts/run-local.py api
.venv/bin/python scripts/run-local.py worker
.venv/bin/python scripts/run-local.py beat
```

```bash
cd frontend
npm ci
npm run build
cd ..
.venv/bin/python scripts/run-local.py frontend
```

El modo local extrae texto mediante herramientas OCR y aplica reglas; no se presenta como un modelo bancario entrenado. Los proveedores Azure requieren credenciales y comprobación independiente. CI comprueba tests del backend, build del frontend y estructura de Compose; no certifica el despliegue completo.

Consulte [arquitectura](docs/architecture.md), [seguridad](docs/security.md) y [despliegue](docs/deployment.md).

Validaciones realizadas y límites: [verificación](docs/verification.md). Para desarrollo desde el código, instalar las dependencias en `.venv` de la raíz y utilizar `.venv/bin/python scripts/run-local.py init`, luego `api`, `worker`, `beat` y `frontend` en terminales separadas. Evitar ejecutar simultáneamente servicios Docker y procesos locales en los mismos puertos.

Acceso desde el navegador, sin instalar programas en Windows: [web en Codespaces](docs/web-gratis.md). Usa la cuota gratuita de GitHub, con límites de horas y almacenamiento; requiere activar el entorno desde tu cuenta.
