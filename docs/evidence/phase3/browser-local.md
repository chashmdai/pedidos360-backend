# Recorrido del frontend local — 2026-09-06

Prueba real en el navegador de Codex con frontend Vite, BFF, Catalog, Orders y MySQL Docker. Hora local UTC−03. El emisor es el fixture RSA local, expresamente identificado en la pantalla; esta ejecución no se presenta como autenticación Microsoft.

| Acción | Resultado observado |
|---|---|
| Inicio sin sesión | Botón Iniciar sesión local; aviso de emisor de pruebas |
| Login local → Catálogo | Dos productos: café 8990 CLP y taza 12990 CLP |
| Crear pedido, cantidades cero | Total $0; Registrar pedido deshabilitado |
| Elegir 2 cafés + 1 taza | Dos líneas seleccionadas; total estimado $30.970; submit habilitado |
| Registrar pedido | Navegación a Mis pedidos; pedido `AA976352…` creado a las 06:36:26, dos líneas, total $30.970 |
| Mis pedidos | Conserva también `21D089B3…` y `4702F199…`; mismo detalle e importes |
| Mi sesión | User, local-development, demo-user y audience/issuer del fixture; sin presentarse como Entra |
| Comprobar acceso Admin | HTTP 403 y mensaje de permiso denegado |
| Cerrar sesión → Mis pedidos | Inicio `/`, sin sesión ni pedidos |

BFF y Orders registraron `POST /api/v1/pedidos 201` a las 06:36:26 y recuperación GET 200. Ver `bff-access.txt` y `orders-service-access.txt`. Catalog respondió 200 a las consultas de los snapshots.

La matriz Python creó además el pedido `5ca7c75c-09cb-45fc-9f6d-d6b121d77a6e` con otro propietario de prueba. Después de reiniciar únicamente los procesos Pedidos360 en modo Entra, una lectura SQL con el usuario de aplicación Orders comprobó ambas cabeceras/líneas y los dos pedidos anteriores de la identidad Microsoft: `persisted-orders.json`.

Al terminar se restauró Entra, se comprobó que el fixture ya no escucha y que su firma es rechazada por el backend. La pestaña quedó en el inicio, con Iniciar sesión y sin aviso de fixture. No se modificó el frontend funcional ni su CSS para este recorrido.
