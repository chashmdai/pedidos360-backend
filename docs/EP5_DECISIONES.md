# Iteración EP5/EP6: decisiones y desviaciones del informe

Este registro complementa `INFORME_EP5_EP6.md` (informe académico). Cada desviación aprobada
se anota aquí para actualizar luego el informe. Las decisiones EP3/EP4 previas siguen en
`DECISIONES.md` y `EP4_DECISIONES.md`, sin cambios.

## Desviaciones respecto del informe

| # | Informe dice | Implementación real | Motivo | Secciones del informe afectadas |
|---|---|---|---|---|
| D-01 | La instancia EP4 `i-0818fdfafcfb7cb31` **se redimensiona** de t3.medium a t3.large (detener, cambiar tipo, iniciar; conserva ID, EBS, IP privada y target del ALB). | Se **crea una EC2 nueva** t3.large en la cuenta nueva; no existe instancia previa que redimensionar. | El laboratorio AWS Academy es nuevo (cuenta `647660738152`); ningún recurso EP4 existe en ella. | 1 (alcance), 13.1, 13.2 paso 1, 16 |
| D-02 | Identificadores EP4: EC2 `i-0818fdfafcfb7cb31`, RDS `pedidos360-mysql` existente, HTTP API `7k2zyh0t0d`, VPC Link y ALB existentes. | Todos los recursos se recrean con **IDs nuevos**, que se registrarán en `docs/evidence/ep5/IDS_NUEVOS.md`. Los IDs antiguos en documentos y journals EP4 se conservan como históricos. | Cuenta nueva (D-01). | 2, 13, E-01, E-17 y cualquier evidencia que cite un ID |
| D-03 | Entorno local de pruebas: **WSL2** (E-18) y usuario `codex`. | **CachyOS (Arch Linux) nativo**, usuario operador regular; Java 25.0.5 Temurin, Maven 3.9.16 (wrapper), Node 26.13, Docker 29.9 + Compose 5.7. | Cambio de máquina de desarrollo. | E-18 (entorno), 18 |
| D-04 | (Implícito) Node 24.20.0 según `.nvmrc`. | Las pruebas y el build del frontend se ejecutan con Node 26.13; resultado idéntico (11 pruebas, build correcto). `.nvmrc` no se modifica. | Versión disponible en la máquina; sin incompatibilidades observadas. | E-18 |
| D-05 | `compose.kafka.yaml` usa "un volumen nombrado por nodo" (4.1). | Cada broker tiene un volumen; cada nodo ZooKeeper tiene **dos** (`…-zookeeper-N-data` y `…-zookeeper-N-log`). | La imagen `cp-zookeeper` fija `dataDir=/var/lib/zookeeper/data` y `dataLogDir=/var/lib/zookeeper/log`, ambos declarados `VOLUME`. Un único volumen con `subpath` falla en un volumen nuevo (Docker exige que el subdirectorio exista) y montarlo en el directorio padre deja el log de transacciones en un volumen anónimo. | 4.1 (texto) |
| D-06 | Procedimientos E-03/E-05/E-06/E-08/E-11: `docker exec kafka-1 kafka-…`. | Mismos comandos, pero ejecutados con `-e KAFKA_HEAP_OPTS=-Xmx128m` (lo hace `scripts/ep5-kafka.sh`). | Las CLI arrancan una JVM dentro del contenedor del broker y heredan `-Xms512m -Xmx512m` (tabla 5). Medido en local: el comando literal sube el contenedor de ~300 a 442 MiB (límite 896 MiB) con el broker en reposo; con el broker cargado el margen se reduce. | E-03, E-05, E-06, E-08, E-11 (procedimiento) |

## Adaptación a Linux nativo (Fase 1)

Alcance mínimo: build, arranque local y cadena de despliegue de la Fase 4. Sin cambios de
comportamiento cuando se usan los valores por defecto anteriores.

- `scripts/ep4-env.sh`: por defecto usa el `aws` del PATH y `~/.aws/credentials`; ambos siguen
  siendo sobreescribibles con `AWS_CLI` y `AWS_SHARED_CREDENTIALS_FILE`. La ruta de Node del
  toolchain WSL solo se añade si existe.
- `scripts/ep4-build.sh`, `ep4-toolchain.sh`, `ep4-session-tools.sh`: la comprobación
  `id -un = codex` se sustituye por "no ejecutar como root". `ep4-session-tools.sh` usa el
  `session-manager-plugin` del sistema si está instalado (en Arch no hay `dpkg-deb`).
- `scripts/aws_deploy.py`: `wslpath` solo se invoca si la CLI es un `.exe` **y** `wslpath` existe.
- `pom.xml`: el perfil `native-wsl-output` se renombra `external-build-root`; se sigue activando
  con `-Dpedidos.build.root` y no cambia el resultado.
- MySQL local: el puerto host es configurable con `PEDIDOS360_MYSQL_PORT` (por defecto 13306).
  `setup-local.sh` lo guarda en `application.env` y `mysql.sh` lo reutiliza. En la máquina actual
  se usa 13307 porque 13306 está ocupado por un contenedor de otro proyecto, que no se toca.
- `scripts/dev.sh start entra|local --with-rabbit`: además de Catalog, Orders, BFF y la SPA,
  inicia receipts (8183), rabbit-admin (8184) y order-insights (8185) contra el clúster
  RabbitMQ EP4 local (`python3 scripts/ep4-broker.py up`). Usa los mismos nombres de variables y
  valores que `deploy/ep4-install.py` en la nube. Los secretos se leen de
  `~/.config/pedidos360/ep4/` (0600), nunca se imprimen. Heaps locales: 384 MiB para los tres
  servicios base y 192 MiB para los de mensajería.

### Scripts conservados como históricos (sin modificar)

`scripts/ep3-*.py|sh`, `scripts/ep3.sh` y `scripts/ep3-publish.py` siguen exigiendo WSL y el
usuario `codex`, o dependen de Windows (PowerShell, Git Credential Manager). Documentan cómo se
produjeron las evidencias EP3 y no forman parte de la cadena EP5. Tampoco se modifican los
generadores de evidencias/PDF de EP4 (`ep4-capture.py`, `ep4-report.py`, `ep4-delivery-check.py`).

## Fase 2A: plataforma Kafka, contratos y productor de Orders

**Versiones fijadas** (por tag y digest del manifiesto multi-arquitectura):

| Imagen | Versión | Digest |
|---|---|---|
| confluentinc/cp-zookeeper | 7.9.10 (Apache ZooKeeper 3.8.6) | sha256:1a870111c6e861f1e6015094fac902779981edb5cb1d2ad6b7437d2a6b8ba064 |
| confluentinc/cp-kafka | 7.9.10 (Apache Kafka 3.9) | sha256:07c3d60362e67c296f7f34b690b1240e5ecdcde4a84f5e73cab320fb4041f58c |
| kafbat/kafka-ui | v1.5.0 | sha256:7cda86a33344160309fdb65146332e4da65db81a945614f2fe32e210803f6fd1 |

Se eligió 7.9.10 (2026-09-16) en lugar de 7.9.11 (2026-11-10) por ser el último parche 7.9.x con más de dos semanas de publicación. Clientes: spring-kafka 4.1.1 y kafka-clients 4.2.1, gestionados por Spring Boot 4.1.1 (serie 4.x, compatible con brokers 3.9). Testcontainers usa la misma imagen cp-kafka 7.9.10.

**Decisiones de implementación** (no contradicen el informe):

- Healthchecks sin JVM adicional: ZooKeeper está healthy solo si `srvr` informa `Mode: leader|follower` (quórum). Un broker está healthy si ambos listeners aceptan conexiones y su nodo efímero `/brokers/ids/<id>` existe (consulta `dump` en ZooKeeper). 4lw habilitados: `srvr,ruok,dump`. Los `VOLUME` de secretos no usados se montan como tmpfs para no crear volúmenes anónimos.
- Kafka UI: `AUTH_TYPE=LOGIN_FORM` con usuario y contraseña en `$PEDIDOS_EP5_CONFIG_DIR/kafka-ui.env` (0600, generado por `ep5-kafka.sh ui up`, nunca impreso). `/actuator/health` es público (para el healthcheck); el resto redirige a `/login`.
- `OrderPersistence` llama ahora a **todos** los `OrderEventRecorder` disponibles (`orderedStream()` en lugar de `ifAvailable`): el registrador RabbitMQ y el de streaming escriben en la misma transacción del pedido. Con un solo registrador el comportamiento EP3/EP4 es idéntico.
- `spring.task.scheduling.pool.size=2` en Orders: el relay Kafka y el publicador RabbitMQ no comparten un único hilo del scheduler, de modo que un Kafka lento no retrasa RabbitMQ.
- `KafkaOutboxRelay` envía el lote de forma asíncrona y espera las confirmaciones con un límite total de 35 s (`pedidos.kafka.relay.confirm-timeout-ms`, mayor que `delivery.timeout.ms=30000`). Si `send()` falla de forma síncrona (sin metadatos del clúster), el resto del lote se aplaza sin reintentarlo en el mismo ciclo. La propiedad de productor de la tabla 10 no se amplía (no se fija `max.block.ms`).
- Los records validan además coherencias que el informe implica: `lineTotal = unitPrice × quantity`, `total = Σ lineTotal`, `itemCount = |items|`, productos únicos y `metricKey` igual a sus componentes. Toda violación lanza `StreamContractException` (no reintentable).
- Prueba existente ajustada: `OrdersIntegrationTest` esperaba 2 migraciones Flyway; ahora espera 3 por `V3__order_stream_outbox.sql` (exigida por el informe). Es el único cambio en pruebas EP3/EP4.
- Si Kafka no está disponible al arrancar Orders, KafkaAdmin registra el error y el servicio arranca igual (unos 10 s más lento); los eventos quedan en la outbox.
- `scripts/dev.sh start entra --with-kafka` activa la outbox de streaming de Orders contra el Compose local.

## Fase 2B: sales-stream-service y ruta del BFF

- **Idempotencia por eventId:** `processed_stream_event` (PK `event_id`, más `order_id` y `consumer_group`) se inserta con `INSERT IGNORE` en la misma transacción que el upsert atómico de `product_sales_daily` (`INSERT … AS n ON DUPLICATE KEY UPDATE … version=version+1`). Si la fila ya existía, no se modifica ningún acumulado. La transacción usa READ COMMITTED y actualiza las claves en orden estable para evitar interbloqueos entre los tres consumidores.
- **Duplicado frente a recuperación:** un evento ya procesado vuelve a publicar los estados actuales; son completos, así que republicar es inocuo. Así se cubre el caso en que el commit ocurrió y la publicación falló (sección 8.3). Se registra `CONSUME_DUPLICATE` cuando es una reentrega (intento 1) y `CONSUME_OK result=METRICS_REPUBLISHED` cuando es un reintento de la misma entrega.
- **Descarte por version:** `LiveSalesView` conserva por `metricKey` solo el estado de version estrictamente mayor; las versiones menores o iguales se descartan (`STALE_VERSION_DISCARDED`).
- **DLT:** la clase `DeadLetterPublishingRecoverer` publica en `<tópico>.DLT` en la misma partición. Para registros no deserializables usa los bytes originales y para los agotados por reintentos el JSON del DTO. Los errores de deserialización y `StreamContractException` no se reintentan. Los transitorios usan backoff exponencial 1 s → 2 s (3 intentos; `ExponentialBackOffWithMaxRetries(2)`). Como el agregador y el monitor leen el mismo tópico, **cada grupo que falla escribe su propia copia** en el DLT, identificada por la cabecera `kafka_dlt-original-consumer-group` (más tópico, partición, offset y excepción de origen).
- **Logs:** `CONSUME_RETRY` solo cuando habrá otro intento; `CONSUME_DLT … code=CONTRACT_INVALID|DESERIALIZATION_FAILED|TRANSIENT_<excepción> retried=…`. El `eventId` de un mensaje no deserializable se extrae de sus bytes si es JSON (si no, `unknown`). También: `ORDER_ALERT`, `METRIC_PUBLISHED` y `DASHBOARD_REBUILD`.
- **Regla de alto valor:** `total ≥ pedidos.streams.alerts.high-value` (50000) solo en la moneda `pedidos.streams.alerts.high-value-currency=CLP`, porque importes de otras monedas no son comparables. Más de `pedidos.streams.alerts.max-lines=10` líneas genera `MUCHAS_LINEAS`. Las alertas se deduplican por eventId y se conservan las 50 más recientes.
- **Endpoint en vivo:** `GET /api/v1/ventas/en-vivo` devuelve solo el día UTC en curso y solo el tenant del claim `tid` del token (que además debe coincidir con el tenant configurado), con `Cache-Control: no-store`. Contrato: `contracts/live-sales-response-v1.schema.json`, referenciado desde `contracts/openapi.yaml`. Nombres de campo en español, como el resto de la API REST.
- Persistencia de sales-stream con JDBC (sin JPA): las sentencias atómicas de upsert son el núcleo del caso de uso.
- **Importes canónicos:** la columna JSON de MySQL devuelve `8990.0` para `8990.00`. Los records de `kafka-support` normalizan los importes a escala 2 después de validarlos, así que el mensaje Kafka siempre lleva dos decimales, como el ejemplo del informe.
- Esquema `pedidos360_streams` local: `docker/mysql/init-databases.sh` es idempotente y se puede re-ejecutar sobre un volumen existente (`bash scripts/mysql.sh exec -T mysql bash /docker-entrypoint-initdb.d/10-pedidos360.sh`) tras `setup-local.sh`, que genera las dos contraseñas nuevas sin tocar las existentes.
- Prueba de punta a punta local sobre el clúster de 3 brokers (RF 3, min ISR 2, `acks=all`) con el emisor JWT de pruebas: POST 201 → `PUBLISH_CONFIRMED` → agregador, monitor (`ORDER_ALERT`) y dashboard → `GET /api/v1/ventas/en-vivo` por el BFF en ~1,2 s; grupos con la distribución de la tabla 11.

## Fase 2C: kafka-admin-service

- Estructura `api` / `application` / `configuration` / `security`, como `rabbit-admin-service`. Usa un único `Admin` (AdminClient) de larga vida con `request.timeout.ms=5000` y `default.api.timeout.ms=10000`, de modo que un clúster que no responde da 503 en lugar de bloquear. No declara `NewTopic` (`spring.kafka.admin.auto-create=false`); lee de `pedidos-kafka.properties` solo los nombres de negocio que protege.
- Seguridad propia del servicio (no importa `messaging-support`, que es AMQP), con la misma regla: rol Admin **y** `SCOPE_Orders.Read` en `/api/v1/admin/kafka/**`.
- Códigos de la sección 10: crear un tópico con nombre fuera de `pedidos360.lab.` (o con nombre de negocio) responde **400**, porque el nombre es un parámetro inválido de la creación. Eliminar o ampliar particiones de un tópico de negocio, DLT, interno (`__*`) o fuera del prefijo responde **409** (protegido). PATCH de configuraciones se permite en tópicos de laboratorio y de negocio (el informe solo restringe crear, ampliar y eliminar), pero no en internos (409). Valores acotados: `retention.ms` −1 o 1 min..1 año; `segment.ms` 1 min..7 días; `min.insync.replicas` 1..3 y no mayor que el RF; `max.message.bytes` 1 KiB..10 MiB; `cleanup.policy` delete/compact/ambas.
- `GET /consumer-groups` usa `listGroups()` sin filtro de tipo KIP-848 (brokers 3.9 en modo ZooKeeper) e incluye, como `kafka-consumer-groups --list`, los grupos de protocolo `consumer` y los "simples" (solo offsets confirmados).
- `GET /consumer-groups/{groupId}`: por partición, el offset confirmado (null si aún no hay), el log-end offset, el lag y el miembro asignado, más `totalLag`. Un grupo inexistente (estado DEAD) responde 404.
- Contrato `contracts/kafka-admin-openapi.yaml`. `OpenApiContractTest` verifica que el contrato, la tabla 14 y el controlador expongan exactamente las mismas 9 operaciones.
- Referencia local de E-14 (fixture Admin, clúster de 3 brokers): `docs/evidence/ep5/local/E-14-kafka-admin-local-referencia.txt`.

## Fase 3: vista "Ventas en vivo" (repositorio frontend)

- Ruta protegida `/ventas-en-vivo` y enlace "Ventas en vivo" en la navegación principal. Consulta `GET /ventas/en-vivo` mediante el cliente API central (mismo bearer MSAL) al montarse y luego cada 3 s **después de terminar** la consulta anterior (sin solapamientos). Se detiene al cerrar la vista y ante 401/403. Ante errores transitorios conserva los últimos datos y sigue consultando.
- Muestra el día UTC, el total del día por moneda (nunca suma monedas distintas), los acumulados por producto (unidades, pedidos, importe, version), las alertas recientes y la hora de la última actualización correcta (y la del último evento procesado).
- Reutiliza solo clases existentes (`page`, `section-title`, `section-rule`, `order-list`, `order`, `badge`, `empty`, `loading-state`, `config-status`); `style.css` no cambia (el hash del CSS de producción es idéntico al de la línea base).
- Pruebas Vitest sin dependencias nuevas: el sondeo se prueba con temporizadores falsos y la vista con `react-dom/server`.

## Fase 4: cadena de despliegue para la cuenta nueva (preparada, sin ejecutar)

- `config/aws-target.json` fija el destino: cuenta 647660738152, journal y evidencias en `docs/evidence/ep5/aws/`, t3.large, raíz de 30 GiB, AMI `ami-0719278fd447e399f` (Ubuntu 24.04, Canonical, 20261118) y MySQL 8.4.11. `aws_deploy.py`, `entra_config.py`, `ep4-ssm.py` y `ep4-transfer.py` lo leen; los secretos van a `~/.config/pedidos360/aws-647660738152/`.
- `compute` ya no importa un par de claves ni abre SSH temporal desde la IP del operador (en EP4 se abrió y luego se cerró). Todo el acceso es por SSM; la AMI se valida por dueño y nombre antes de lanzar.
- `gateway` crea en una sola etapa las 8 rutas JWT (incluida `GET /api/v1/ventas/en-vivo` con `Orders.Read`) y las 2 rutas GET públicas de la SPA, que en EP4 añadía `ep4-gateway.py`.
- `deploy/ep5-install.py` consolida en un instalador idempotente lo que en EP4 hacían `install-release.py`, `ep4-host-prepare.py` y `ep4-install.py`, más EP5: swap, Docker, esquema `pedidos360_streams`, Kafka y Kafka UI, y los 8 servicios con los heaps de la tabla 16. El arranque escalonado usa `After=` en cadena y un `ExecStartPost` que espera `/actuator/health` UP antes de iniciar el siguiente. Las unidades Compose (`pedidos360-rabbit-cluster`, `-kafka-cluster`, `-kafka-ui`) arrancan antes.
- Los heaps de receipts, rabbit-admin e insights pasan de 128 MiB (EP4) a 192 MiB, según la tabla 16.
- La identidad guardada en evidencias omite el nombre de sesión del ARN (contiene el correo de quien abrió el laboratorio).
- **Throttling de API Gateway:** EP4 usaba 5 rps / ráfaga 10 en el stage `$default` (journal de fase 5 y `gateway-after.json` de EP4). En EP5 se sube a **10 rps / ráfaga 20**, a pedido del usuario: la SPA carga varias rutas a la vez y la vista en vivo consulta cada 3 s, y la demo no debe recibir 429. Sigue siendo un límite bajo de laboratorio.
- **apt solo por HTTPS:** el SG de la EC2 permite salir solo por 443. Al inicio, el bootstrap reemplaza `/etc/apt/sources.list.d/ubuntu.sources` por fuentes explícitas `https://archive.ubuntu.com` y `https://security.ubuntu.com` (antes era un `sed` sobre la réplica regional) y verifica `apt-get update` con reintentos. Si falla, se detiene sin marcar `bootstrap-complete`. No se abre el puerto 80.
- Aprobación del checkpoint: el usuario aprobó la creación de los recursos y las etapas 1 a 9 el 2026-11-19, con los dos ajustes anteriores.
- Detalle de recursos, seguridad, orden y costo: [EP5_AWS_CHECKPOINT.md](EP5_AWS_CHECKPOINT.md).

## Pendientes

- `npm audit` informa 4 vulnerabilidades (2 moderadas, 2 altas) en dependencias del frontend;
  por indicación del usuario no se tratan en esta iteración.
