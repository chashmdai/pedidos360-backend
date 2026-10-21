# Iteración EP4: decisiones y límites

## Base reconciliada

El 2026-10-21 comprobé la cuenta AWS 002996184293, rol voclabs y región us-east-1. El inventario actual está en `evidence/ep4/aws-inventory.json` y la inspección SSM en `evidence/ep4/instance-inspection.json`. La EC2 propia i-0818fdfafcfb7cb31 es t3.medium (3832 MiB), tiene 16 GiB libres y los tres servicios anteriores saludables. RDS pedidos360-mysql está disponible. Los siete identificadores de rutas coinciden con el journal. No ejecuté los scripts antiguos de creación ni modifiqué sus evidencias.

## Evolución elegida

- Mantener Orders, su outbox transaccional y su publicación confirmada en el exchange direct existente. Mantener Receipts y sus nombres/contrato.
- Incorporar un exchange topic conectado al direct mediante binding entre exchanges. Dos consumidores independientes materializan una auditoría de pedidos y los datos para un resumen diario por moneda. Cada flujo tiene su cola principal, DLX y DLQ. No enviar correos ficticios ni simular pagos/inventario.
- Agrupar los dos nuevos consumidores en `order-insights-service`, por responsabilidad de consulta analítica/auditoría. Mantener separados sus paquetes, persistencia y decisiones ACK/NACK. Los archivos se escriben de forma atómica; los resúmenes se calculan desde eventos únicos, sin sumar dos veces una redelivery.
- Dos nodos RabbitMQ 4.2.9 en Compose, volúmenes propios y cookie externa a Git. Mantener intacto el broker/volumen EP3 local. Puertos de EP4 ligados únicamente a loopback. Colas classic durables: sus mensajes **no se replican**. Un clúster de dos nodos, especialmente en una EC2, no es HA; no prometer continuidad ante pérdida de nodo/host ni consenso disponible con una minoría. Las pruebas distinguirán parada temporal con conservación de volúmenes y tolerancia a fallos.
- Reutilizar EC2, RDS, ALB interno, VPC Link y API Gateway. Servir la compilación React en `/app/` por BFF y el Gateway HTTPS existente. Solo las rutas GET de archivos SPA serán públicas; `/api/v1` conserva JWT/scopes. No añadir S3/CloudFront, balanceadores, instancias, discos ni capacidad. Sigue existiendo el costo de uso/tráfico de los recursos actuales.
- Mantener perfiles, diseño visual, contratos y scopes `Catalog.Read`, `Orders.Read`, `Orders.Create`. Añadir únicamente soporte de ruta base a React/MSAL. El fixture local no se desplegará.

## Checkpoint Entra: URI cloud

La SPA existente es `b4ede06a-cde3-4982-8b79-56fab7264fdd` en tenant `72fd0b5a-8a6a-4cff-89f6-bde961f7e250`. Para iniciar OAuth2 desde el hosting cloud hace falta autorizar exactamente:

`https://7k2zyh0t0d.execute-api.us-east-1.amazonaws.com/app/`

Acción aprobada y ejecutada una sola vez: después de autenticar manualmente y leer la configuración real mediante Microsoft Graph, añadí esa URI a `spa.redirectUris` de la SPA existente. La lectura posterior confirmó la conservación de las dos URI locales, scopes, roles y permisos. No cambié consentimientos, propietarios, usuarios ni políticas. La sesión CLI inicialmente exigió autenticación (AADSTS50173); el usuario la completó personalmente, sin elevar permisos. Evidencia: [antes](evidence/ep4/entra-spa-before.json), [después](evidence/ep4/entra-spa-after.json) y [prueba institucional cloud](evidence/ep4/entra-browser.json).

## Fuentes técnicas

- [RabbitMQ 4.2: clustering y límites de dos nodos](https://www.rabbitmq.com/docs/4.2/clustering).
- [RabbitMQ 4.2: particiones](https://www.rabbitmq.com/docs/4.2/partitions).
- [AWS: instalación de CLI en directorio del usuario](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html). Instalé CLI Linux 2.38.3 bajo el HOME de codex porque la CLI Windows no podía leer los temporales privados Linux; no modifiqué credenciales. `ep4-env.sh` solo configura variables del proceso y referencia el archivo ya existente del operador.

Estas son decisiones de implementación; el PDF oficial prevalece sobre las comprobaciones propuestas en el anexo. No son una calificación ni evidencia de pruebas aún no ejecutadas.
