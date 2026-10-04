# Abrir la aplicación como web sin instalar programas en Windows

## Opción verificada: cuota personal de GitHub Codespaces

GitHub documenta una cuota mensual gratuita para cuentas personales: **120 horas de núcleo** (aproximadamente 60 horas con una máquina de 2 núcleos) y **15 GB-mes de almacenamiento** en el plan Free. La cuota se comparte con otros Codespaces de la misma cuenta. Sin medio de pago registrado, agotar la cuota **bloquea el uso**; no se agrega una tarjeta ni se activa facturación desde este proyecto.

Esto permite ejecutar la web con usuarios, base de datos, documentos, antivirus, OCR y workflow reales en la nube. **No es alojamiento permanente 24/7 ni un despliegue de producción.** El entorno se detiene por inactividad y debe reanudarse desde GitHub. El almacenamiento también consume cuota cuando está detenido. La disponibilidad, condiciones y política de retención pertenecen a GitHub; no se promete gratuidad ilimitada ni permanencia indefinida.

Fuente oficial comprobada: [facturación y cuota Codespaces](https://docs.github.com/en/billing/concepts/product-billing/github-codespaces). Se verificó el texto del repositorio oficial `github/docs`, incluyendo la regla de bloqueo sin medio de pago.

Hugging Face Docker Spaces se descartó: la documentación oficial consultada exige actualmente un plan pago para crear Spaces Docker/Gradio con cómputo. Las páginas estáticas gratuitas no ejecutan este backend. Netlify estático tampoco sustituye OCR, almacenamiento ni la base de datos.

## Pasos del usuario

[Crear el entorno de la web](https://github.com/codespaces/new?repo=1403670916&ref=codex%2Fweb-gratuita). Este enlace abre la creación del entorno; no es una dirección de una aplicación ya desplegada.

1. Iniciar sesión en la cuenta GitHub personal que tiene acceso al repositorio. No agregar tarjeta ni aceptar actualizaciones pagas. Si ya hay un medio de pago registrado, revisar el presupuesto y bloqueo de uso excedente antes de crear el entorno.
2. Abrir el enlace de creación de Codespace entregado para la rama preparada. Elegir **2 núcleos**. No seleccionar máquinas más grandes ni prebuilds. Si GitHub pide pago, no continuar.
3. Esperar a que termine la preparación automática. Se construyen y arrancan los servicios dentro de GitHub; no se instala nada en Windows.
4. En el explorador de archivos del Codespace abrir `.workflow/ABRIR-WEB.md`. Presionar **Ctrl+Shift+V** para ver la vista previa y hacer clic en **Abrir la aplicación web**. Ese enlace privado lleva la clave de primera configuración en un fragmento, no en una consulta del servidor.
5. Elegir nombre, email y contraseña del administrador en la propia web. Luego iniciar sesión. No hay datos bancarios ni usuarios ficticios precargados.
6. Para volver a entrar, reanudar el mismo Codespace desde [tus Codespaces](https://github.com/codespaces) y abrir su puerto **WorkFlow Créditos** o el enlace generado. No crear un entorno nuevo cada vez: cada uno tiene datos y cuota propios.
7. Al terminar, usar **Stop codespace**. Revisar el consumo y respaldar base, objetos y claves antes de borrar o reconstruir el entorno. No subir `.env`, `.workflow` ni documentos al repositorio público.

El puerto 3000 conserva la visibilidad privada predeterminada de Codespaces. Su conexión interna al contenedor es HTTP porque Next no sirve TLS; el enlace externo usa HTTPS del proveedor. Los demás servicios no se exponen como aplicación pública. Para que otras personas entren sin una cuenta GitHub hay que evaluar abrir el puerto, después de crear el administrador y revisar permisos/seguridad; no se cambia su visibilidad automáticamente.

## Alcance

Se ejecuta el stack de nueve servicios existente: PostgreSQL, Redis, Azurite, ClamAV, Mailpit, API, worker, scheduler e interfaz. Azurite almacena documentos cifrados en un volumen del entorno; es una solución de desarrollo, no Azure gestionado. El OCR y las reglas/plantillas son locales al servidor y no requieren una API paga. Azure generativo no está configurado. Mailpit captura correo de prueba; las notificaciones internas sí funcionan y el correo externo sigue requiriendo un proveedor autorizado.

Los datos se montan desde carpetas privadas en `.workflow/data`, dentro de `/workspaces`, para conservarlos fuera de las capas temporales de los contenedores. Un borrado del Codespace o una política de retención puede perderlos. No hay respaldo remoto automático en esta configuración. Mantener copias coordinadas de PostgreSQL, objetos y claves fuera del Codespace. No almacenar datos bancarios reales antes de revisión específica de seguridad y cumplimiento.

## Implementación

`.devcontainer/devcontainer.json` usa la imagen estándar de Codespaces y Docker dentro del entorno. `scripts/codespaces_start.py` conserva secretos existentes, prepara origen HTTPS y cookies seguras, crea una clave de setup protegida y arranca Compose. El archivo de enlace y `.env` se excluyen de Git. Las claves no se imprimen ni se pasan como parámetros de comandos.

La configuración inicial web es opt-in y requiere una clave de 32+ caracteres. El servidor bloquea la creación si ya existe cualquier usuario, serializa solicitudes concurrentes, verifica origen y limita intentos. No incorpora registro público ni contraseñas por defecto. La clave del fragmento se elimina del historial al cargar el formulario y no queda en auditoría.

La integración de esta sesión puede leer el repositorio pero devolvió `Resource not accessible by integration` al consultar máquinas Codespaces y facturación. No se creó ni activó un Codespace ni se comprobó el consumo de la cuenta. La creación debe hacerse desde la cuenta del usuario; un archivo de configuración guardado o un enlace de creación no equivale a una web ya publicada.

## Validación realizada

Pasaron 36 pruebas backend con PostgreSQL real y dos pruebas de preparación de configuración. El build Next.js y su comprobación TypeScript pasaron. Chromium comprobó el formulario inicial, creación real del administrador, retirada del fragmento privado, ausencia de la clave en almacenamiento del navegador, login, dashboard y layout móvil. Compose comprobó los cuatro montajes de datos en carpetas ignoradas del workspace. No se comprobó todavía el arranque de este perfil dentro de GitHub Codespaces.
