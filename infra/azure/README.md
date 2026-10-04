# Base Azure para revisión

`main.bicep` expresa una base propuesta: Azure Blob privado con versionado, Key Vault con RBAC y protección de purga, PostgreSQL, Redis, Log Analytics y un entorno Container Apps. No se desplegó ni compiló en esta máquina; revisar compatibilidad de API, región, SKU y costes antes de usarlo.

La red pública de datos está deshabilitada deliberadamente. **La plantilla no constituye un despliegue funcional de la aplicación:** todavía deben añadirse VNet, endpoints privados y DNS, integración de red de Container Apps, asignaciones de identidad administrada, contenedores de aplicación, secretos Key Vault, ingress TLS, job de migraciones, reglas de escalado, antivirus y políticas de backup/retención. No habilitar acceso público para resolver estas dependencias.

La elección Redis es una base de compatibilidad de Celery; revisar Azure Managed Redis y las fechas de retirada de Azure Cache for Redis antes de producción. PostgreSQL sin HA es únicamente una base inicial y debe adaptarse al objetivo de disponibilidad. El cifrado AES-GCM de aplicación requiere una clave administrada separada.

Validación propuesta en una estación con Azure CLI/Bicep:

```bash
az bicep build --file infra/azure/main.bicep
# Revisar un what-if con parámetros seguros y sus permisos antes de desplegar.
```

No guardar la contraseña PostgreSQL en archivos versionados ni pasarla en argumentos registrados. El template no genera usuarios comerciales ni datos de clientes y no envía correo. Su mera presencia no acredita cumplimiento bancario ni recursos externos creados.
