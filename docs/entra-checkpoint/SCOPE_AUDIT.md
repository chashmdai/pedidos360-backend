# Auditoría de scopes antes de registrar Entra

Checkpoint aprobado por el usuario el 2026-09-05. Se revisaron frontend, BFF, Catalog, Orders, contratos, tests, emisor local y manifiestos propuestos antes de cualquier escritura Graph.

Los nombres canónicos son **Catalog.Read**, **Orders.Read** y **Orders.Create**, respetando mayúsculas. No se encontró `Orders.Write` en el código/configuración/contratos actuales. No es necesario renombrar scopes existentes.

Los tres Resource Servers convierten los valores de `scp` a autoridades `SCOPE_*`. Crear un pedido exige `SCOPE_Orders.Create` y `SCOPE_Catalog.Read`; consultar pedidos exige `SCOPE_Orders.Read`. Los contratos y tests usan esos mismos valores. El fixture frontend local solicita un token con los tres nombres.

En modo Entra el frontend toma `VITE_API_SCOPES`, todavía vacío en `.env.example`; tras registrar la API se configurará con las tres URI completas `api://<nuevo-api-client-id>/<nombre-canónico>`. No se confundirá el nombre de scope con su prefijo URI ni con el GUID de audience. La preautorización y requiredResourceAccess referencian exactamente los tres GUID definidos en el manifiesto 01.

Decisión: conservar **Orders.Create** como permiso para registrar solicitudes; no introducir el alias Orders.Write ni ampliar a edición de pedidos.
