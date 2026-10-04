# Despliegue

## Entorno local

`./scripts/dev-up.sh` genera secretos locales si falta `.env` y ejecuta Compose. Inicia PostgreSQL, Redis, Azurite, ClamAV, Mailpit, API, worker, beat e interfaz. Azurite es el emulador oficial de Azure Blob para desarrollo; Mailpit captura mensajes localmente y no envía correo a destinatarios externos.

La API ejecuta migraciones y catálogo antes de servir peticiones. Comprobar logs, disponibilidad del almacenamiento y firmas del antivirus antes de cargar documentos. Beat programa comprobaciones SLA cada cinco minutos; mantener una sola instancia. Los volúmenes conservan datos entre reinicios. Respaldar PostgreSQL, objetos y claves de cifrado de forma coordinada; probar restauración. `docker compose down -v` destruye datos.

En la máquina de validación se utilizó `FRONTEND_PORT=3100` por puertos ocupados. `PUBLIC_ORIGIN` debe incluir el origen real de la interfaz. La respuesta de `/api/health` indica disponibilidad HTTP, no certifica almacenamiento, OCR, firmas o Azure externo.

## Azure de producción

No se han creado recursos externos. El diseño propone Azure Container Apps para frontend/API/worker, PostgreSQL Flexible Server, Redis administrado, Azure Blob privado y Key Vault. Configurar identidad administrada, permisos mínimos y acceso privado. La conexión compartida de Azurite es exclusivamente local; producción requiere configuración Azure real y evaluación de permisos.

Los objetos se cifran en la aplicación con AES-256-GCM. Conservar y gestionar `STORAGE_ENCRYPTION_KEY` de forma segura; su pérdida impide descifrar documentos. Evaluar versionado y rotación antes de producción. El cifrado adicional del servicio Blob y las políticas de claves son controles separados.

Azure AI Document Intelligence y Azure OpenAI son opcionales. Configurar endpoints y credenciales en un gestor de secretos y comprobar cada adaptador con documentos autorizados. No hay validación externa sin credenciales. Usar SMTP autorizado con STARTTLS; Mailpit no demuestra entrega externa.

## Antes de publicar

1. Construir imágenes versionadas, analizar vulnerabilidades y fijar digests.
2. Configurar redes privadas, TLS, secretos, dominio y origen de interfaz; `COOKIE_SECURE=true` en producción.
3. Ejecutar migraciones como job controlado antes de ampliar réplicas, evitando ejecución concurrente.
4. Configurar probes, límites, escalado, reintentos y alertas. Verificar carga, OCR, revisión y recepción de notificaciones.
5. Ensayar backup/restauración y rollback; migraciones pueden requerir correcciones o restauración.
6. Completar revisión de seguridad y cumplimiento de la organización responsable.

## Proxy de construcción

Un builder puede tener una red distinta del host. Configurar los argumentos estándar `http_proxy`/`https_proxy` y DNS; un `--add-host` autorizado del proxy puede resolver una configuración DNS incompleta. Backend y frontend admiten el secreto opcional BuildKit `environment_ca`, proporcionando un bundle confiable con `--secret id=environment_ca,src=/ruta/bundle.pem`. La CA se usa durante pip/npm sin copiarse al contenedor. Mantener TLS, firmas y checksums; no deshabilitar verificación.

MinIO fue descartado después de comprobar que el binario oficial devolvía HTTP 410 y se retiró como servicio por defecto. El almacenamiento local utiliza Azure Blob/Azurite. En la máquina cloud, las capas de la imagen MCR de Azurite estaban bloqueadas; se usó el paquete oficial npm `azurite@3.35.0`, verificado por npm, para generar una imagen local de validación. `AZURITE_IMAGE` permite ese override local; el valor por defecto de Compose sigue siendo la imagen oficial MCR. No publicar la imagen alternativa sin revisión y un proceso de construcción reproducible.

Las firmas ClamAV incluidas eran del 27 de septiembre de 2026. La actualización requiere acceso a `database.clamav.net` y debe comprobarse antes de datos reales.

La última comprobación HTTP del servidor de firmas recibió 403; la actualización automática sigue pendiente de resolver y verificar.

## Evidencia de validación local

Se comprobó un flujo real con Azure Blob/Azurite: cuatro documentos cifrados, análisis antivirus, OCR, identificación de RUT incorrecto, sustitución de documento por el cliente, validación humana, descarga autorizada, SLA comercial, envío y asignación a Riesgos, solicitud de información una sola vez, pausa y reenvío, aprobación, dashboard y exportaciones PDF/Excel/Word. Se verificó la cadena de auditoría y recepción local en Mailpit. Esta validación acredita la implementación inicial en desarrollo; no equivale a una evaluación de seguridad, cumplimiento o disponibilidad de producción.

La alternativa Azurite reproducible se encuentra en [infra/azurite](../infra/azurite/README.md), con versión fijada, lockfile y `npm ci`. El proceso usado inicialmente generó una imagen local a partir de esos paquetes oficiales; la receta guardada permite reconstruirla sin copiar secretos.
