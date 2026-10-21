# Evidencia de Admin temporal — 2026-09-06

El usuario informó que no tiene acceso a la contraseña de Jazmín y aprobó expresamente sustituir esa prueba por Admin temporal en su propia cuenta. No se autenticó a Jazmín ni se modificó su asignación.

1. El selector de Microsoft mostró la cuenta anterior y Usar otra cuenta. El flujo de Jazmín llegó a contraseña y se abandonó mediante Atrás; no se ingresó ninguna contraseña para ella.
2. Se registró únicamente Admin temporal para be.torrejons@duocuc.cl. El usuario completó su inicio de sesión real y Microsoft devolvió la SPA.
3. Mi sesión mostró `Admin · User`, los tres scopes, audience `114f7b58-b207-4d46-9d6e-f491c3a0c0e0`, cliente `b4ede06a-cde3-4982-8b79-56fab7264fdd`, tenant esperado, issuer v2 y su mismo oid. Token emitido 01:24:37, válido hasta 02:32:25 hora local UTC−03.
4. Comprobar acceso Admin mostró `Consulta Admin: HTTP 200. 1 pedidos en el tenant.` La ruta administrativa respondió 200 tanto en BFF como Orders, registrado en access logs a las 01:30:40 y 01:31:07.
5. La vista Pedidos del tenant reutilizó el diseño existente. Se creó un pedido con 2 cafés + 1 taza, total 30970 CLP. BFF y Orders registraron `POST /api/v1/pedidos 201` a las 01:31:36. Catalog registró los GET de ambos snapshots con 200. La recuperación mostró el nuevo pedido `91CEA5F7…` y el anterior `4A53BD04…`, cada uno de dos líneas, sin cambiar sus importes. BFF/Orders registraron GET pedidos 200 a las 01:31:37.
6. Se retiró solo la asignación temporal. Graph confirmó a las 04:32:26 UTC que las dos asignaciones originales son idénticas a la lectura previa: Benjamin→User y Jazmín→Admin. Evidencia en `../entra/10-removal-verification.json`.

Completado el cierre a las 06:31 hora local: un token renovado desde Microsoft mostró solo User y recibió 403 en la ruta administrativa. Logout retornó a la SPA y las cinco rutas protegidas redirigieron al inicio en la misma pestaña. Ver [browser-final.md](browser-final.md). No se afirma revocación inmediata de un JWT ya emitido.
