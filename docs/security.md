# Seguridad y límites

Esta base necesita revisión de seguridad antes de tratar datos financieros reales. Ejecutar localmente con datos de prueba propios y minimizados.

## Configuración

Generar secretos independientes para sesiones, base de datos y almacenamiento. `.env` está excluido del repositorio; `.env.example` contiene marcadores y no debe usarse en producción. En producción, inyectar secretos mediante un gestor de secretos y rotarlos. No incluir datos personales, claves o documentos en logs ni instrucciones de instalación.

La configuración local usa `COOKIE_SECURE=false` para HTTP y `PUBLIC_ORIGIN=http://localhost:3000`. En producción usar `COOKIE_SECURE=true`, HTTPS y el origen real de la interfaz.

Usar TLS en el acceso público y conexiones internas según el modelo de amenazas. Limitar PostgreSQL, Redis, almacenamiento y antivirus a redes privadas. Compose publica API, interfaz y consola de almacenamiento únicamente en localhost; usar un túnel autorizado para acceso remoto de desarrollo.

## Documentos y decisiones

Verificar el antivirus antes de habilitar cargas. Sus firmas deben estar actualizadas; un fallo del servicio no debe permitir publicar documentos sin analizar. Aplicar límites de tamaño, tipo y número de páginas. La extracción de documentos y el texto enviado a modelos son datos no confiables; instrucciones dentro de documentos no deben autorizar operaciones.

Los hallazgos automáticos no sustituyen una evaluación humana de crédito. Antes de activar Azure, revisar región, tratamiento de datos, términos, retención, registros y acceso. No enviar documentos reales a proveedores sin autorización de la organización.

## Requisitos de producción pendientes

Revisar autorización por objeto y rol, MFA/SSO, CSRF según el mecanismo de sesión, expiración y revocación, rate limiting, protección contra fuerza bruta, cifrado y gestión de claves, auditoría resistente a modificaciones, copia y restauración, retención y borrado, análisis de dependencias, pruebas de penetración y normativa aplicable. La presencia de un módulo o variable de configuración no prueba que un control esté certificado ni que todos estos requisitos estén implementados.

## Cifrado de objetos

Los documentos se cifran en la aplicación con AES-256-GCM y una clave aleatoria de 32 bytes configurada en `STORAGE_ENCRYPTION_KEY`. La cuenta Azurite local usa una clave base64 independiente de 64 bytes. Conservar la clave de cifrado de forma segura junto al plan de recuperación: perderla impide recuperar los documentos. En producción, gestionar claves en Azure Key Vault y revisar rotación/versionado antes de usar datos reales. Azurite es un emulador oficial para desarrollo, no un servicio de producción.

Mailpit captura el correo exclusivamente en desarrollo sin TLS. En producción utilizar un proveedor SMTP autorizado, STARTTLS y credenciales administradas; la recepción local de un mensaje no acredita entrega externa.
