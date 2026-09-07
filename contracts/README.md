# Contratos de integración

Esta carpeta contiene contratos HTTP y documentación técnica. **No es un `common-domain`**: no contiene Product, Order, aggregates, repositorios, servicios de dominio ni entidades JPA compartidas.

`openapi.yaml` describe la superficie mínima del BFF. Catalog publica las rutas de productos; Orders publica las de pedidos. Cada servicio implementa sus propios DTO y traducciones. Los consumidores dependen de la representación HTTP, no de clases del productor.

Los tests `CatalogIntegrationTest`, `OrdersIntegrationTest` y `BffContractTest` verifican respuestas HTTP reales, campos relevantes, propagación del bearer y códigos de estado. La especificación todavía no genera clientes ni reemplaza esos tests.

El POST recibe exclusivamente identificadores y cantidades. Orders consulta Catalog, fija snapshots de nombre/precio/moneda y obtiene el propietario desde `tid` + `oid` del JWT validado. El precio y el propietario enviados por el cliente no son fuentes de verdad.

El estado `REGISTERED` significa solicitud registrada. No confirma pago, reserva de stock ni una operación comercial completada. Stock es referencial. Un reintento de POST puede crear otro pedido; no hay reintento automático ni garantía de idempotencia en este bloque.
