# Evidencia de navegador — User, 2026-09-05

Observación directa mediante navegador Codex y árbol de accesibilidad. Este registro conserva los resultados obtenidos antes de la interrupción de la sesión; no contiene access tokens, contraseñas ni códigos de Authenticator.

- Sin sesión: pulsar Catálogo mantiene/redirige a `/` y muestra Iniciar sesión.
- El flujo Microsoft usa el client ID de la SPA nueva, response_type=code, PKCE S256 y los tres scopes completos de la API, además de openid/profile/offline_access de MSAL.
- El usuario completó Authenticator. Retorno a `http://localhost:5173/`, con navegación Mi sesión y Cerrar sesión.
- `/sesion` mostró los claims devueltos por `/api/v1/me`, tras validación del BFF:

| Campo | Valor observado |
|---|---|
| Cuenta | be.torrejons@duocuc.cl |
| Rol | User |
| Scopes | Catalog.Read, Orders.Create, Orders.Read |
| Tenant | 72fd0b5a-8a6a-4cff-89f6-bde961f7e250 |
| oid propietario | c375a6eb-b82a-44f6-abe0-fe32d7901c3e |
| sub | Og1Lm4w748Bak3hEJj_rQp-9xdeWVyGOFHg2pv4yoKo |
| Audience API | 114f7b58-b207-4d46-9d6e-f491c3a0c0e0 |
| Cliente azp | b4ede06a-cde3-4982-8b79-56fab7264fdd |
| Issuer | https://login.microsoftonline.com/72fd0b5a-8a6a-4cff-89f6-bde961f7e250/v2.0 |
| Versión | 2.0 |
| Primera adquisición | Adquisición silenciosa, desde caché MSAL |

La acción Comprobar acceso Admin mostró literalmente: `Consulta Admin: HTTP 403. Tu cuenta no tiene permiso para esta operación.`

Renovar sesión mostró `Renovación solicitada · desde Microsoft`; la posterior consulta al BFF aceptó el nuevo token. Los valores visibles de emisión/vigencia cambiaron de 19:45:13 / 21:16:26 a 19:47:10 / 21:04:50 del 5 de septiembre (hora local mostrada entonces, UTC−04). No se infiere que renovar deba siempre ampliar exp, ni se presenta como expiración natural o prueba interactiva de fallback. La pantalla indicó expresamente esa limitación.

El catálogo devolvió Café de especialidad (8990 CLP) y Taza de cerámica (12990 CLP). Se registraron 2 cafés + 1 taza: total 30970 CLP. Retorno a Mis pedidos con pedido `4A53BD04…`, fecha visible 05-09-2026 19:53:41, dos líneas, estado Registrado y total correcto. La creación y recuperación se observaron en la UI; el código HTTP exacto de ese POST no se capturó, pues los access logs se activaron después. Los tests de contrato sí habían comprobado 201; las próximas pruebas de navegador registrarán también el estado HTTP del runtime.

Al pulsar Cerrar sesión, Microsoft mostró `Cerró la sesión de su cuenta` y `Cierre todas las ventanas del explorador.` La ejecución se interrumpió en esa pantalla. No se registró retorno automático a la SPA antes de la interrupción. La prueba completa de acceso a rutas después del logout y el flujo Admin continúan en el registro de la siguiente sesión.
