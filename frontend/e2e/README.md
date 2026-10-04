# Pruebas reales en navegador

Ejecutar contra una instancia API y PostgreSQL **aisladas para pruebas**. Nunca usar la base de producción. La cuenta administrativa debe existir en la base de pruebas.

Requisitos: Python con `playwright` y `psycopg`, Chromium (o `CHROMIUM_PATH`). El frontend debe apuntar mediante `API_URL` a la API de pruebas. `E2E_BASE_URL` debe coincidir con `PUBLIC_ORIGIN`.

```bash
E2E_BASE_URL=http://localhost:3000 \
E2E_EMAIL=browser-admin@example.com \
E2E_PASSWORD="$TEST_ADMIN_PASSWORD" \
TEST_DATABASE_URL="$TEST_DATABASE_URL" \
E2E_SYNTHETIC_DOCUMENT_FIXTURE=1 \
python frontend/e2e/critical_flow.py
```

El flag de fixture es obligatorio para este escenario: documentos sintéticos se insertan exclusivamente en una base cuyo nombre contenga `test`. Es una sustitución explícita de los límites externos (object storage, antimalware y OCR), **no valida esas integraciones** ni carga documentación bancaria real. El flujo de registro, propuesta, informe, autoguardado, revisión, envío, asignación y aprobación sí utiliza la interfaz y API reales. Los fallos hacen terminar el script con estado no cero. Las capturas se guardan en `/tmp/workflow-e2e`.

`session_security.py`, con las mismas variables de entorno, verifica el bloqueo inmediato tras una respuesta 401 real y el cierre de la interfaz tras 60 minutos de inactividad usando únicamente un reloj de navegador controlado. No altera el reloj del servidor ni su política de sesión.
