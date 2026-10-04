# Comprobaciones de la implementación

## Resultado actual

La API FastAPI, PostgreSQL persistente, Redis/Celery, almacenamiento privado Azure Blob local (Azurite), ClamAV, correo local Mailpit e interfaz Next.js se ejecutaron en esta máquina. `/api/ready` verificó base de datos, cola, antivirus y almacenamiento. El despliegue en una cuenta Azure externa no se ha realizado.

La suite backend pasó 32 pruebas de autenticación, permisos, aislamiento por cartera/expediente, concurrencia, checklist, workflow, solicitud adicional única, reapertura, SLA/feriados, calidad de informe, auditoría y exportación. Incluye pruebas criptográficas reales de AES-GCM y pruebas de firma temporal ligada a la sesión. Las pruebas unitarias de fronteras externas identifican explícitamente sus mocks.

En la adaptación web actual se ejecutaron 36 pruebas backend y dos de configuración Codespaces. Se añadió la comprobación real de la cola de escritorio/documentos en Linux (Defender sustituido explícitamente) y configuración inicial web con PostgreSQL aislado, clave privada, origen, creación única concurrente, login y auditoría. Chromium verificó configuración inicial, login y dashboard en móvil sobre el frontend compilado. El perfil cloud todavía requiere creación y verificación en Codespaces; no hay un enlace de aplicación desplegada.

## Circuito con servicios reales

```bash
# Desde la raíz del proyecto, con .env y servicios locales activos:
.venv/bin/python backend/tests/integration_real_services.py
```

Este script utiliza exclusivamente `workflow_real_services_test`; crea empresas y usuarios de prueba en esa base aislada. Usa Redis DB 11 y un worker temporal que termina al cerrar la prueba. Nunca envía mensajes externos: Mailpit captura SMTP local.

Se verificó: registro y asignación de empresa; propuesta/checklist; carga desde el portal; antivirus; persistencia de objetos cifrados; OCR de PDF real; detección de RUT incorrecto; sustitución del documento; revisión humana; completitud y validez; SLA comercial; informe asistido y finalización humana; envío a Riesgos; asignación manual; única ampliación; pausa/reinicio SLA; aprobación; estado del portal; notificaciones y SMTP local; dashboard; CSV/XLSX/PDF; cadena íntegra de auditoría. Las descargas firmadas recuperaron el SHA-256 original y rechazaron tokens inválidos.

También se comprobó ClamAV con un archivo limpio y la firma de prueba EICAR, y OCR de imagen con Tesseract. Esto no certifica la actualidad futura de firmas ni exactitud de OCR en documentos del banco.

## Navegador

`frontend/e2e/critical_flow.py` prueba la interfaz con Chromium: creación, informe, envío, asignación, decisión, rúbrica humana y portal. Su fixture documental directo es explícito: esa prueba de interfaz no sustituye la integración documental real anterior. `frontend/e2e/session_security.py` comprueba cierre de sesión/limpieza de pantalla. Los datos de estos scripts pertenecen a una base `_test`.

## Diferencias de alcance

- OCR local es extracción y reglas explicables; la asistencia comercial local es una plantilla con cálculos. El adaptador Azure OpenAI es generativo pero no se verificó sin credenciales.
- Azurite persiste objetos reales con API compatible con Azure Blob; sigue siendo un emulador de desarrollo.
- SMTP local demuestra generación y recepción de notificaciones; la entrega por un proveedor externo no está comprobada.
- La auditoría impide UPDATE/DELETE/TRUNCATE y mutaciones desde la aplicación. Un superusuario de base de datos puede cambiar DDL: se incluye archivo opcional S3 Object Lock COMPLIANCE, no provisionado ni probado contra un servicio externo. Exige administración y credenciales separadas.
- El calendario excluye feriados administrados; antes de operación deben cargar y comprobar los oficiales del año correspondiente.
- Azure Bicep es una base para revisión, sin compilación/despliegue verificados; faltan decisiones y configuración de red privada, identidad y políticas de la organización.
- Rotación/versionado de claves documentales, restauración/DR, carga y penetración requieren validación específica antes de producción. No se afirma conformidad bancaria.
