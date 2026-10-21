# Cierre real de identidad y sesión — 2026-09-06

Registro de observaciones del navegador de Codex y access logs del BFF. Hora local: America/Santiago, UTC−03. No se extrajeron ni guardaron JWT, contraseñas, códigos MFA ni contenido de sessionStorage.

## User después de retirar Admin

La asignación Admin temporal se había retirado a las 04:32:26 UTC; `../entra/10-removal-verification.json` confirma que se conservaron exactamente las dos asignaciones originales. En esta continuación no se ejecutaron escrituras ni nuevas consultas Graph.

Al retomar, la SPA ya estaba autenticada con Benjamin. `/sesion` mostró solo `User`, con un token emitido a las 06:21:30 y válido hasta las 07:34:09. Se pulsó **Renovar sesión** para comprobar además una adquisición nueva desde Microsoft:

| Dato observado y aceptado por el BFF | Valor |
|---|---|
| Identidad | be.torrejons@duocuc.cl |
| Roles | User; sin Admin |
| Scopes | Catalog.Read · Orders.Create · Orders.Read |
| Versión | 2.0 |
| Audience | 114f7b58-b207-4d46-9d6e-f491c3a0c0e0 |
| Cliente azp | b4ede06a-cde3-4982-8b79-56fab7264fdd |
| Tenant | 72fd0b5a-8a6a-4cff-89f6-bde961f7e250 |
| oid | c375a6eb-b82a-44f6-abe0-fe32d7901c3e |
| Emisor | https://login.microsoftonline.com/72fd0b5a-8a6a-4cff-89f6-bde961f7e250/v2.0 |
| Emitido / válido hasta | 06:25:50 / 07:44:09 |
| Adquisición | Renovación solicitada · desde Microsoft |

La pantalla confirmó que la API aceptó el token. El BFF registró `GET /api/v1/me 200` a las 06:30:51. **Comprobar acceso Admin** mostró `Consulta Admin: HTTP 403. Tu cuenta no tiene permiso para esta operación.` El log registra `GET /api/v1/admin/pedidos 403` a las 06:31:06.

Esto comprueba el estado del token nuevo. No implica revocación inmediata de JWT anteriores ni prueba de expiración natural. La primera renovación inmediatamente posterior a retirar el rol había conservado Admin durante la propagación; no se contabilizó como éxito de esta comprobación.

## Logout y protección de rutas

Se pulsó **Cerrar sesión** desde `/sesion`. El flujo salió a Microsoft y regresó automáticamente a `http://localhost:5173/` con el parámetro de estado del logout. La SPA mostró **Iniciar sesión**, sin nombre de cuenta ni enlace Mi sesión. No fue necesario cambiar la configuración Entra ni el frontend.

Después se navegó directamente, en la misma pestaña y sin volver a iniciar sesión:

| Ruta solicitada | Resultado observado |
|---|---|
| /pedidos | Inicio `/`, sin sesión ni pedidos |
| /catalogo | Inicio `/`, sin sesión ni productos |
| /nuevo | Inicio `/`, sin sesión ni formulario |
| /sesion | Inicio `/`, sin sesión ni claims |
| /administracion | Inicio `/`, sin sesión ni datos administrativos |

Son redirecciones del router React; no se describen como HTTP 302. La seguridad de los datos reside también en el backend: las comprobaciones HTTP finales sin token, token malformado y firma del fixture obtuvieron 401 en los tres procesos configurados con Entra.

## Evidencia HTTP y límites

- `bff-access.txt`, `orders-service-access.txt` y `catalog-service-access.txt` son copias de logs reales hasta este cierre, antes de cambiar al fixture para FASE 3. Solo contienen fecha, método, ruta sin query, código y duración.
- Admin temporal: GET administrativo 200 en BFF y Orders a las 01:30:40; POST pedido 201 en ambos a las 01:31:36; recuperación 200. Detalle en `browser-admin-temporary.md`.
- User restaurado: `/me` 200 y Admin 403 con token renovado; códigos registrados arriba.
- `entra-runtime-http.json`: 23 comprobaciones aprobadas a las 09:31:33 UTC; discovery/JWKS oficiales, health, rechazos JWT y CORS. El archivo conserva la última repetición a las 09:38:28 UTC al restaurar Entra después de las pruebas locales. No usa un token válido de Microsoft; la evidencia autenticada es la del navegador.
- La sesión real de ja.pissani@duocuc.cl **no se ejecutó** por falta de disponibilidad de sus credenciales/MFA. Graph acredita su asignación Admin. El comportamiento funcional Admin se probó mediante la variante temporal expresamente autorizada.

FASE 2 queda cerrada con ese límite de evidencia aceptado por el usuario. No se realizó ninguna operación AWS.
