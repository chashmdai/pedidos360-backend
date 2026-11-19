**INFORME ACADÉMICO / IMPLEMENTACIÓN Y VALIDACIÓN**

Pedidos360

Streaming de eventos con Apache Kafka

*Documentación de las etapas EP5 y EP6 — Desarrollo Cloud Native I (DSY1107)*

**Autores**

Jazmín Pissani

Benjamín Torrejón

**Período documentado** 18–26 de noviembre de 2026

**Alcance**

El documento describe la incorporación de Apache Kafka a Pedidos360 como plataforma de streaming y analítica, complementaria a la mensajería RabbitMQ construida en EP3 y EP4. Se exponen la arquitectura Kafka con ZooKeeper y tres brokers, el diseño de tópicos y eventos, los productores, consumidores y grupos de consumidores, el manejo de errores, la administración de la plataforma y su despliegue en AWS. Por indicación docente, las evidencias se registran como texto y no como imágenes.

# 1. Objetivo y alcance

El objetivo de esta etapa es incorporar procesamiento de eventos en streaming al registro de pedidos de Pedidos360, de modo que la solución pueda calcular indicadores de venta por producto, detectar pedidos que requieren atención y exponer esa información en cuasi tiempo real, sin modificar los contratos REST, la identidad ni la mensajería RabbitMQ existentes. Kafka se incorpora como un canal adicional y paralelo: RabbitMQ continúa entregando el trabajo puntual de comprobantes, auditoría y resumen diario con confirmaciones por mensaje, y Kafka conserva un registro particionado, replicado y releíble de los eventos de pedido para su consumo analítico por varios grupos independientes.

El alcance comprende un clúster Kafka de tres nodos ZooKeeper y tres brokers levantado con Docker Compose; Kafka UI levantado con un archivo Compose propio; dos tópicos de negocio con tres particiones y factor de replicación tres, más sus tópicos de mensajes fallidos; un productor en orders-service alimentado por una outbox transaccional propia; un nuevo microservicio sales-stream-service con tres grupos de consumidores; un microservicio kafka-admin-service para la administración de tópicos, configuraciones y grupos; una vista “Ventas en vivo” en la SPA; y el despliegue completo de la solución en una nueva cuenta de AWS Academy Learner Lab, sobre una instancia EC2 t3.large.

La documentación distingue entre el diseño implementado en el código, las pruebas automatizadas y las comprobaciones ejecutadas en AWS. La sección 15 reúne las evidencias en formato textual: cada una declara su objetivo, el indicador asociado, el entorno, el procedimiento y el resultado. Las cifras de capacidad son valores de diseño y no constituyen mediciones de rendimiento o disponibilidad productiva.

# 2. Línea base heredada de EP3 y EP4

Al inicio de esta etapa, Pedidos360 contaba con seis servicios Spring Boot 4.1.1 sobre Java 25, una SPA React 19 con TypeScript y MSAL, y bases MySQL 8.4 separadas por contexto en Amazon RDS. La SPA se sirve en la ruta /app/ y consume las API a través de API Gateway HTTP, VPC Link y un ALB interno que llega al BFF en la instancia EC2. Todas las rutas de negocio validan JWT de Microsoft Entra ID (issuer, audience, tenant, azp, versión 2.0 y scopes Catalog.Read, Orders.Read y Orders.Create).

En mensajería, EP3 incorporó una outbox transaccional en Orders, publicación con publisher confirms y el servicio de comprobantes con ACK manual, NACK sin reencolado y DLQ. EP4 amplió la topología a un clúster RabbitMQ 4.2.9 de dos nodos, un exchange direct enlazado a un exchange topic y tres colas con sus respectivas DLQ. Esta etapa conserva esa topología, el contrato OrderRegisteredV1 y los nombres de colas, exchanges y bindings sin modificaciones.

| **Componente**             | **Responsabilidad**                                                            | **Puerto (loopback)** | **Etapa**  |
|----------------------------|--------------------------------------------------------------------------------|-----------------------|------------|
| **bff**                    | Integración para la SPA; reenvío con el access token a destinos internos fijos | 8180                  | Base       |
| **catalog-service**        | Catálogo de productos y snapshots de precio                                    | 8181                  | Base       |
| **orders-service**         | Pedidos multítem, outbox RabbitMQ y, desde EP5, outbox Kafka                   | 8182                  | Base / EP5 |
| **receipts-service**       | Comprobantes de recepción desde RabbitMQ                                       | 8183                  | EP3        |
| **rabbit-admin-service**   | Administración REST de colas, exchanges y bindings                             | 8184                  | EP3        |
| **order-insights-service** | Auditoría y resumen diario desde RabbitMQ                                      | 8185                  | EP4        |
| **sales-stream-service**   | Agregación de ventas, alertas y vista en vivo desde Kafka                      | 8186                  | EP5        |
| **kafka-admin-service**    | Administración de tópicos, configuraciones y grupos Kafka                      | 8187                  | EP5        |

Tabla 1. Microservicios de Pedidos360 al término de EP5.

# 3. Kafka como complemento de RabbitMQ

RabbitMQ y Kafka resuelven necesidades distintas dentro de Pedidos360. RabbitMQ entrega cada mensaje a una cola y lo elimina tras la confirmación del consumidor, lo que se ajusta a tareas que deben ejecutarse una vez y con control individual de fallos, como emitir un comprobante. Kafka mantiene los eventos en un registro particionado durante un período de retención, y cada grupo de consumidores avanza con su propio offset; por ello varios procesos pueden leer el mismo flujo de forma independiente, a su propio ritmo, e incluso releerlo.

| **Aspecto**           | **RabbitMQ (EP3–EP4)**                                             | **Kafka (EP5)**                                                 |
|-----------------------|--------------------------------------------------------------------|-----------------------------------------------------------------|
| **Modelo**            | Colas con entrega y confirmación por mensaje                       | Registro particionado, replicado y retenido en el tiempo        |
| **Consumo**           | Consumidores que compiten por una cola; enrutamiento por exchanges | Grupos de consumidores con offsets independientes por partición |
| **Relectura**         | No; el mensaje confirmado se elimina                               | Sí, dentro de la retención o del estado compactado              |
| **Fallos**            | NACK sin reencolado hacia DLQ                                      | Reintentos con backoff y publicación en tópico DLT              |
| **Uso en Pedidos360** | Comprobante, auditoría y resumen diario por evento                 | Indicadores por producto, alertas y vista en cuasi tiempo real  |

Tabla 2. Roles complementarios de RabbitMQ y Kafka.

Para no acoplar ambos canales, orders-service registra dos eventos en la misma transacción que persiste el pedido: el evento RabbitMQ existente en la tabla order_event_outbox y un evento de streaming en una tabla nueva, order_stream_outbox. Cada tabla tiene su propio publicador y ambos registros se insertan en la misma transacción. Si Kafka no está disponible, los eventos de streaming quedan pendientes y RabbitMQ sigue operando; si RabbitMQ no está disponible, ocurre lo inverso. La creación del pedido conserva su respuesta síncrona HTTP 201 en ambos casos. Además, los dos publicadores se ejecutan en hilos distintos del planificador de Orders, de modo que un Kafka lento no retrasa la publicación en RabbitMQ.

El flujo completo de un pedido, desde su registro hasta la vista en vivo, se desarrolla en los siguientes pasos:

1.  La SPA envía POST /api/v1/pedidos a través de API Gateway; Orders valida el JWT, consulta snapshots en Catalog y persiste pedido, evento RabbitMQ y evento de streaming en una única transacción MySQL.

2.  El publicador RabbitMQ existente procesa order_event_outbox sin cambios (comprobante, auditoría y resumen diario).

3.  El relay Kafka de Orders lee order_stream_outbox, publica OrderRegisteredStreamV1 en pedidos360.orders.registered.v1 con clave orderId y marca la fila como publicada solo después de la confirmación acks=all.

4.  El grupo pedidos360-sales-aggregator, con tres consumidores, actualiza los acumulados por producto, día UTC y moneda, y publica el estado resultante en pedidos360.sales.product-metrics.v1.

5.  El grupo pedidos360-order-monitor evalúa en paralelo la regla de pedidos de alto valor y genera alertas.

6.  El grupo pedidos360-sales-dashboard materializa el último estado de cada métrica; la SPA lo consulta cada tres segundos mediante GET /api/v1/ventas/en-vivo.

# 4. Arquitectura Kafka con Docker Compose

## 4.1. Componentes y versiones

El clúster utiliza las imágenes de Confluent Platform 7.9.x, basadas en Apache Kafka 3.9. Se eligió esta línea porque es la última que incluye ZooKeeper: a partir de Apache Kafka 4.0 y Confluent Platform 8.0 el modo ZooKeeper fue retirado en favor de KRaft. Se utiliza el parche 7.9.10 (Apache ZooKeeper 3.8.6 y Apache Kafka 3.9), fijado en los archivos Compose por etiqueta y por digest; se prefirió al parche más reciente por tener más de dos semanas de publicación. Los servicios Spring Boot 4.1.1 utilizan spring-kafka 4.1.1 y kafka-clients 4.2.1, compatibles con brokers 3.9.

| **Servicio Compose**                      | **Imagen**                       | **Rol**                            | **Exposición**                    |
|-------------------------------------------|----------------------------------|------------------------------------|-----------------------------------|
| **zookeeper-1, zookeeper-2, zookeeper-3** | confluentinc/cp-zookeeper:7.9.10 | Ensamble de coordinación (IDs 1–3) | Solo red interna pedidos360-kafka |
| **kafka-1, kafka-2, kafka-3**             | confluentinc/cp-kafka:7.9.10     | Brokers (broker.id 1–3)            | 127.0.0.1:19092, 19093 y 19094    |
| **kafka-ui**                              | kafbat/kafka-ui:v1.5.0           | Administración y supervisión web   | 127.0.0.1:8090                    |

Tabla 3. Servicios de la arquitectura Kafka.

La arquitectura se define en dos archivos: compose.kafka.yaml levanta los tres nodos ZooKeeper y los tres brokers, con volúmenes nombrados por nodo (uno por broker y dos por nodo ZooKeeper, porque la imagen separa el directorio de datos del registro de transacciones) y la red pedidos360-kafka; compose.kafka-ui.yaml levanta Kafka UI y se conecta a esa red como red externa. Ninguno de los dos archivos referencia contenedores, redes o volúmenes de RabbitMQ o MySQL, por lo que pueden iniciarse y detenerse sin afectar la mensajería existente.

## 4.2. Rol de los nodos ZooKeeper

ZooKeeper almacena los metadatos del clúster en modo ZooKeeper: el registro de brokers activos, la elección del broker controlador, la definición de tópicos y particiones y sus configuraciones. Los tres nodos forman un ensamble que opera por mayoría: con tres miembros, el quórum es de dos, de modo que el ensamble tolera la caída de un nodo. Si fallan dos, el clúster pierde la capacidad de modificar metadatos, por ejemplo elegir un nuevo controlador o crear tópicos. Cada nodo declara ZOOKEEPER_SERVER_ID y la lista ZOOKEEPER_SERVERS con los puertos 2888 (sincronización) y 3888 (elección de líder); el puerto cliente 2181 no se publica al host.

## 4.3. Rol de los brokers

Los brokers almacenan las particiones de los tópicos y atienden a productores y consumidores. Cada partición tiene un líder, que recibe las escrituras y lecturas, y seguidores que replican su registro. Las réplicas sincronizadas con el líder conforman el conjunto ISR (in-sync replicas). Uno de los brokers actúa como controlador, elegido a través de ZooKeeper, y reasigna el liderazgo de las particiones cuando un broker deja de responder. Con tres brokers y tres particiones por tópico, el liderazgo se distribuye a razón de una partición líder por broker, lo que reparte la carga de escritura.

## 4.4. Tolerancia a fallos

La combinación de tres réplicas por partición, min.insync.replicas=2 en los tópicos y acks=all en los productores define el comportamiento ante fallos. Una escritura se confirma cuando al menos dos réplicas la registran; por lo tanto, la pérdida de un broker no elimina datos confirmados ni detiene las escrituras.

| **Escenario**                | **Comportamiento esperado**                                                                                                                               |
|------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Cae un nodo ZooKeeper**    | El ensamble mantiene quórum (2 de 3); el clúster continúa sin cambios visibles.                                                                           |
| **Cae un broker**            | El controlador elige nuevos líderes entre las réplicas del ISR; el ISR baja a 2, que cumple min.insync.replicas, y productores y consumidores continúan.  |
| **Caen dos brokers**         | El ISR queda en 1 réplica; las escrituras con acks=all se rechazan (NotEnoughReplicas) y la outbox conserva los eventos pendientes hasta la recuperación. |
| **Se reincorpora un broker** | Sus réplicas se ponen al día desde los líderes y vuelven al ISR.                                                                                          |
| **Cae el host EC2**          | Todos los nodos se detienen. Esta topología no ofrece alta disponibilidad frente a la pérdida del host (ver sección 16).                                  |

Tabla 4. Escenarios de fallo considerados.

Adicionalmente, unclean.leader.election.enable=false impide que una réplica desactualizada asuma el liderazgo, privilegiando la consistencia por sobre la disponibilidad, y auto.create.topics.enable=false evita que un error de nombre cree tópicos con valores por defecto.

## 4.5. Parámetros de los brokers

| **Parámetro**                                          | **Valor**         | **Justificación**                                                |
|--------------------------------------------------------|-------------------|------------------------------------------------------------------|
| **default.replication.factor**                         | 3                 | Igual al número de brokers; cada partición conserva tres copias. |
| **min.insync.replicas**                                | 2                 | Escritura confirmada en al menos dos réplicas con acks=all.      |
| **num.partitions**                                     | 3                 | Valor por defecto alineado con los tópicos de negocio.           |
| **offsets.topic.replication.factor**                   | 3                 | Los offsets de los grupos también se replican.                   |
| **transaction.state.log.replication.factor / min.isr** | 3 / 2             | Coherencia del registro interno de transacciones.                |
| **unclean.leader.election.enable**                     | false             | Evita la pérdida de datos confirmados.                           |
| **auto.create.topics.enable**                          | false             | Los tópicos se crean de forma explícita y versionada.            |
| **KAFKA_HEAP_OPTS (brokers)**                          | -Xms512m -Xmx512m | Dimensionado para la instancia t3.large compartida.              |
| **KAFKA_HEAP_OPTS (ZooKeeper)**                        | -Xmx256m          | Carga de metadatos baja en el laboratorio.                       |

Tabla 5. Configuración del clúster en compose.kafka.yaml.

## 4.6. Red, listeners y seguridad

Cada broker declara dos listeners: INTERNAL (kafka-N:29092), usado por los brokers entre sí y por Kafka UI dentro de la red Docker, y EXTERNAL (127.0.0.1:1909N), usado por los servicios Spring que corren como procesos systemd en el host. Ningún puerto Kafka, ZooKeeper ni de Kafka UI se publica fuera de loopback; el acceso operativo a Kafka UI se realiza mediante reenvío de puertos de AWS Systems Manager, el mismo mecanismo empleado en EP4 para la consola de RabbitMQ. Kafka UI exige inicio de sesión con credenciales almacenadas fuera del repositorio. El tráfico entre servicios y brokers dentro del host no está cifrado; esta decisión se declara como limitación.

# 5. Diseño de tópicos

## 5.1. Tópicos de negocio y de mensajes fallidos

| **Tópico**                                  | **Propósito**                                   | **Clave**                       | **P / R** | **Política**    |
|---------------------------------------------|-------------------------------------------------|---------------------------------|-----------|-----------------|
| **pedidos360.orders.registered.v1**         | Flujo de pedidos registrados                    | orderId                         | 3 / 3     | delete, 7 días  |
| **pedidos360.sales.product-metrics.v1**     | Último acumulado por producto, día UTC y moneda | tenantId:productId:fecha:moneda | 3 / 3     | compact         |
| **pedidos360.orders.registered.v1.DLT**     | Eventos de pedido no procesables                | Clave original                  | 3 / 3     | delete, 14 días |
| **pedidos360.sales.product-metrics.v1.DLT** | Métricas no procesables                         | Clave original                  | 3 / 3     | delete, 14 días |

Tabla 6. Tópicos de Pedidos360 (P: particiones; R: factor de replicación).

Los dos tópicos de negocio son los que exige la evaluación; los tópicos DLT son auxiliares, mantienen el mismo número de particiones para que cada mensaje fallido conserve su partición de origen y se distinguen por el sufijo .DLT.

## 5.2. Parámetros por flujo de datos

| **Parámetro**                 | **orders.registered.v1** | **product-metrics.v1**   | **Tópicos DLT**      |
|-------------------------------|--------------------------|--------------------------|----------------------|
| **cleanup.policy**            | delete                   | compact                  | delete               |
| **retention.ms**              | 604800000 (7 días)       | No aplica (compactación) | 1209600000 (14 días) |
| **min.insync.replicas**       | 2                        | 2                        | 2                    |
| **segment.ms**                | 86400000 (1 día)         | 3600000 (1 hora)         | 86400000 (1 día)     |
| **min.cleanable.dirty.ratio** | No aplica                | 0.1                      | No aplica            |
| **delete.retention.ms**       | No aplica                | 86400000 (1 día)         | No aplica            |
| **max.message.bytes**         | 1048576                  | 1048576                  | 1048576              |

Tabla 7. Configuración de administración de cada tópico.

El flujo de pedidos usa una política delete con retención de siete días: es un historial de hechos que debe poder releerse durante una ventana acotada, por ejemplo para incorporar un nuevo grupo de consumidores o reprocesar tras una corrección. El flujo de métricas usa compactación: cada mensaje representa el estado completo de un acumulado, por lo que basta conservar el último valor de cada clave. Un segmento de una hora y un min.cleanable.dirty.ratio de 0,1 permiten que la compactación ocurra dentro de la ventana de laboratorio. Los DLT retienen catorce días para dar tiempo al diagnóstico.

## 5.3. Justificación de tres particiones

La partición es la unidad de paralelismo de Kafka: dentro de un grupo, cada partición se asigna a un único consumidor. Con tres particiones, el grupo pedidos360-sales-aggregator ejecuta tres consumidores simultáneos y cada uno procesa una partición; un cuarto consumidor quedaría ocioso. Tres particiones coinciden además con el número de brokers, de modo que cada broker lidera una partición de cada tópico y la carga de escritura se reparte de forma uniforme. Kafka garantiza orden solo dentro de una partición, por lo que la elección de la clave determina qué eventos conservan su orden relativo. Aumentar las particiones más adelante es posible, pero cambia la correspondencia entre clave y partición; por eso el número se fija desde el diseño.

## 5.4. Justificación de tres réplicas

El factor de replicación tres mantiene cada partición en los tres brokers. Junto con min.insync.replicas=2 y acks=all, garantiza que todo evento confirmado exista al menos en dos brokers, y permite que el clúster siga aceptando escrituras con un broker detenido. El factor de replicación no puede superar el número de brokers; con tres brokers, tres es el máximo y entrega la mayor resiliencia disponible en esta topología.

## 5.5. Claves y orden

En pedidos360.orders.registered.v1 la clave es orderId. Cada pedido genera un único evento, por lo que no existe un orden entre eventos de un mismo pedido que preservar, y una clave aleatoria como un UUID distribuye los eventos de forma pareja entre las tres particiones. En pedidos360.sales.product-metrics.v1 la clave identifica el acumulado (tenant, producto, día UTC y moneda); así, todas las actualizaciones de un mismo acumulado llegan a la misma partición en orden, y la compactación conserva la más reciente. Cada métrica incluye además un campo version creciente que permite descartar una actualización más antigua si llegara fuera de orden.

## 5.6. Definición declarativa y reproducible

Los nombres y parámetros de los tópicos se centralizan en el módulo kafka-support, en el archivo pedidos-kafka.properties, de forma análoga a pedidos-rabbit.properties en messaging-support. Los servicios declaran los tópicos como beans NewTopic construidos con TopicBuilder; KafkaAdmin los crea al iniciar si no existen y no altera los ya existentes. El script scripts/ep5-kafka.sh ofrece además las operaciones de infraestructura por línea de comandos (levantar y detener los Compose, crear, describir y configurar tópicos, e inspeccionar grupos), de modo que la plataforma puede reconstruirse de forma replicable.

# 6. Diseño de los eventos

## 6.1. OrderRegisteredStreamV1

El evento de pedido registrado para streaming amplía la información del contrato RabbitMQ con las líneas del pedido, necesarias para calcular indicadores por producto sin consultar Catalog ni Orders. Se define como record Java inmutable con validación en su constructor y como JSON Schema en contracts/order-registered-stream-v1.schema.json.

| **Campo**                           | **Tipo y regla**                      | **Razón de su inclusión**                                              |
|-------------------------------------|---------------------------------------|------------------------------------------------------------------------|
| **schemaVersion**                   | Entero, igual a 1                     | Permite evolucionar el contrato y rechazar versiones desconocidas.     |
| **eventId**                         | UUID                                  | Identidad del evento; base de la idempotencia de los consumidores.     |
| **orderId**                         | UUID                                  | Clave del mensaje y correlación con el pedido y con el flujo RabbitMQ. |
| **tenantId**                        | Texto, 1–100 caracteres               | Aísla los acumulados por tenant de Entra ID.                           |
| **occurredAt**                      | Fecha y hora ISO-8601 en UTC          | Determina el día UTC del acumulado y la latencia observada.            |
| **currency**                        | Código ISO 4217 de tres letras        | Los importes solo se suman dentro de una misma moneda.                 |
| **total**                           | Decimal no negativo, dos decimales    | Evaluación de la regla de pedidos de alto valor.                       |
| **itemCount**                       | Entero, 1–50                          | Coherencia con items y regla de pedidos voluminosos.                   |
| **items\[\].productId**             | UUID                                  | Identifica el producto del acumulado.                                  |
| **items\[\].productName**           | Texto, 1–120 caracteres               | Snapshot del nombre; la vista no depende de Catalog.                   |
| **items\[\].quantity**              | Entero, 1–1000                        | Unidades vendidas del acumulado.                                       |
| **items\[\].unitPrice / lineTotal** | Decimales no negativos, dos decimales | Importe solicitado por línea, fijado al registrar el pedido.           |

Tabla 8. Estructura de OrderRegisteredStreamV1.

El evento no incluye el oid del usuario, su nombre, su correo ni tokens: la analítica opera sobre agregados por tenant y no requiere identidad personal, siguiendo el mismo principio de minimización del contrato OrderRegisteredV1. Ejemplo de mensaje (clave: valor de orderId):

> {
>
> "schemaVersion": 1,
>
> "eventId": "6f1c2b0e-8d4a-4f7b-9e21-3c5a7d9b1e40",
>
> "orderId": "b2e4c6a8-1f3d-4b5a-8c7e-9d0f2a4b6c81",
>
> "tenantId": "72fd0b5a-8a6a-4cff-89f6-bde961f7e250",
>
> "occurredAt": "2026-11-24T14:05:12.345678Z",
>
> "currency": "CLP",
>
> "total": 30970.00,
>
> "itemCount": 2,
>
> "items": \[
>
> { "productId": "…", "productName": "…", "quantity": 1,
>
> "unitPrice": 18990.00, "lineTotal": 18990.00 },
>
> { "productId": "…", "productName": "…", "quantity": 2,
>
> "unitPrice": 5990.00, "lineTotal": 11980.00 }
>
> \]
>
> }

## 6.2. ProductSalesMetricV1

La métrica publicada en el tópico compactado representa el estado completo de un acumulado, no un incremento. Esta decisión hace que volver a publicar la misma métrica sea inocuo y que un consumidor pueda reconstruir el estado leyendo el tópico desde el inicio.

| **Campo**                            | **Tipo y regla**                      | **Razón de su inclusión**                                     |
|--------------------------------------|---------------------------------------|---------------------------------------------------------------|
| **schemaVersion**                    | Entero, igual a 1                     | Versionado del contrato.                                      |
| **metricKey**                        | Texto tenantId:productId:fecha:moneda | Coincide con la clave del mensaje; facilita la inspección.    |
| **tenantId, productId, productName** | Texto, UUID y texto                   | Identifican el acumulado y su presentación.                   |
| **businessDate**                     | Fecha AAAA-MM-DD en UTC               | Período del acumulado diario.                                 |
| **currency**                         | ISO 4217                              | Moneda del acumulado.                                         |
| **unitsSold, ordersCount**           | Enteros no negativos                  | Unidades y pedidos que incluyen el producto.                  |
| **revenue**                          | Decimal, dos decimales                | Importe solicitado acumulado (no representa pagos).           |
| **version**                          | Entero largo, creciente por clave     | Descarta actualizaciones antiguas que lleguen fuera de orden. |
| **lastEventId, updatedAt**           | UUID y fecha ISO-8601                 | Trazabilidad hacia el evento que produjo el estado.           |

Tabla 9. Estructura de ProductSalesMetricV1.

## 6.3. Validación y evolución

Ambos records validan en su constructor los rangos, formatos y la versión del esquema; un payload que no cumple el contrato produce una excepción de contrato que el manejador de errores clasifica como no reintentable. Los mensajes se serializan como JSON con Jackson y sin encabezados de tipo Java, de modo que los consumidores deserializan hacia su propio tipo y no dependen del nombre de clase del productor. Agregar campos opcionales mantiene la versión; un cambio incompatible exige un nuevo tópico con sufijo .v2 y un período de convivencia.

# 7. Productores

## 7.1. Outbox de streaming en orders-service

La migración Flyway V3\_\_order_stream_outbox.sql crea la tabla order_stream_outbox con la misma estructura de control que la outbox de EP3: identificador del evento, identificador del pedido, payload JSON, fecha de creación y de publicación, número de intentos, próxima fecha de intento y último código de error. Un registrador StreamOutboxRecorder inserta el evento OrderRegisteredStreamV1 en la misma transacción que persiste el pedido; si la transacción se revierte, no queda evento huérfano.

El componente KafkaOutboxRelay se ejecuta cada segundo, selecciona hasta veinte filas pendientes con FOR UPDATE SKIP LOCKED, envía cada evento mediante KafkaTemplate y espera la confirmación del broker. Solo cuando el envío se confirma con acks=all registra published_at y escribe en el log PUBLISH_CONFIRMED con eventId, orderId, tópico, partición y offset. Si el envío falla o vence el tiempo de espera, incrementa los intentos, programa un nuevo intento en cinco segundos y registra PUBLISH_DEFERRED con el código KAFKA_UNCONFIRMED.

## 7.2. Productor de métricas en sales-stream-service

Después de confirmar en base de datos la actualización de un acumulado, sales-stream-service lee el estado resultante de cada producto afectado y publica un ProductSalesMetricV1 en pedidos360.sales.product-metrics.v1, con la clave del acumulado y la misma configuración de productor confiable.

## 7.3. Configuración del productor

| **Propiedad**                                | **Valor**                                       | **Propósito**                                                        |
|----------------------------------------------|-------------------------------------------------|----------------------------------------------------------------------|
| **bootstrap.servers**                        | 127.0.0.1:19092,127.0.0.1:19093,127.0.0.1:19094 | Los tres brokers; el cliente descubre el resto del clúster.          |
| **key.serializer**                           | StringSerializer                                | Claves textuales (UUID o clave compuesta).                           |
| **value.serializer**                         | Serializador JSON de Spring for Apache Kafka    | DTO tipados sin encabezados de tipo Java.                            |
| **acks**                                     | all                                             | Confirmación por todas las réplicas del ISR.                         |
| **enable.idempotence**                       | true                                            | El broker descarta duplicados causados por reintentos del productor. |
| **max.in.flight.requests.per.connection**    | 5                                               | Máximo compatible con idempotencia y orden por partición.            |
| **delivery.timeout.ms / request.timeout.ms** | 30000 / 10000                                   | Límite total de entrega y de cada solicitud.                         |
| **linger.ms / compression.type**             | 5 / lz4                                         | Agrupación breve de mensajes y menor uso de red y disco.             |
| **client.id**                                | Nombre del servicio                             | Identificación del productor en logs y métricas.                     |

Tabla 10. Propiedades del productor Kafka.

# 8. Consumidores y grupos de consumidores

## 8.1. Grupos definidos

| **Grupo**                       | **Tópico**           | **Consumidores** | **Inicio**                         | **Responsabilidad**                                      |
|---------------------------------|----------------------|------------------|------------------------------------|----------------------------------------------------------|
| **pedidos360-sales-aggregator** | orders.registered.v1 | 3                | earliest                           | Acumulados por producto, día y moneda; publica métricas. |
| **pedidos360-order-monitor**    | orders.registered.v1 | 1                | latest                             | Alertas de pedidos de alto valor o voluminosos.          |
| **pedidos360-sales-dashboard**  | product-metrics.v1   | 1                | Desde el inicio en cada asignación | Vista en vivo del último estado de cada métrica.         |

Tabla 11. Grupos de consumidores de sales-stream-service.

Los grupos combinan los dos modos de consumo de Kafka. Entre grupos distintos, cada uno recibe todos los eventos: el agregador y el monitor leen el mismo tópico con offsets independientes, de modo que una demora en el cálculo de acumulados no retrasa las alertas. Dentro de un grupo, las particiones se reparten entre sus consumidores: los tres consumidores del agregador procesan una partición cada uno. Si un consumidor se detiene, el coordinador del grupo reasigna su partición a los restantes; se utiliza CooperativeStickyAssignor para que el reequilibrio solo mueva las particiones afectadas.

El monitor inicia en latest para no emitir alertas sobre pedidos antiguos la primera vez que se despliega; el agregador inicia en earliest para incorporar todos los eventos retenidos. El grupo de la vista implementa ConsumerSeekAware y se posiciona al inicio del tópico compactado cada vez que recibe particiones, reconstruyendo en memoria el último estado de cada métrica.

## 8.2. Separación entre mensajería y lógica

sales-stream-service mantiene la organización domain, application e infrastructure del resto de los servicios. Los listeners con @KafkaListener pertenecen a infrastructure y se limitan a recibir el DTO, registrar el contexto (tópico, partición, offset) y delegar en los casos de uso: SalesAggregationService, OrderAlertPolicy y LiveSalesView, escritos en Java sin dependencias de Kafka. Esta separación permite probar la lógica de negocio sin broker y sustituir el transporte sin modificarla.

## 8.3. Procesamiento del agregador

Por cada evento, el agregador abre una transacción en la base pedidos360_streams e inserta el eventId en processed_stream_event. Si el identificador ya existe, el evento es un duplicado: no modifica acumulados, registra CONSUME_DUPLICATE y confirma el offset. Si es nuevo, actualiza product_sales_daily con una sentencia de inserción o actualización atómica que suma unidades, pedidos e importe e incrementa version. Tras el commit, publica las métricas resultantes y solo entonces se confirma el offset del evento.

Si la publicación de la métrica falla después del commit, el evento se reintenta: el control de duplicados evita sumar dos veces y la métrica, al ser un estado completo, se vuelve a publicar sin efectos indebidos. La atomicidad de la base de datos permite además que los tres consumidores actualicen simultáneamente acumulados de un mismo producto sin perder incrementos. El esquema pedidos360_streams se crea en la misma instancia RDS, con usuarios propios de aplicación y de migración, TLS con VERIFY_IDENTITY y Flyway, siguiendo el patrón de Catalog y Orders.

## 8.4. Monitor de pedidos y vista en vivo

OrderAlertPolicy genera una alerta cuando el total de un pedido alcanza el umbral configurado en pedidos.streams.alerts.high-value (50.000 CLP en el laboratorio; la regla se evalúa solo en CLP porque importes de monedas distintas no son comparables) o cuando el pedido supera diez líneas. Cada alerta se registra en el log como ORDER_ALERT y se conserva en una lista acotada de las cincuenta más recientes. LiveSalesView mantiene, por clave, la métrica de mayor version y expone ambos conjuntos en GET /api/v1/ventas/en-vivo, filtrados por el tenant del JWT.

## 8.5. Configuración del consumidor

| **Propiedad**                               | **Valor**                                                                 | **Propósito**                                                                  |
|---------------------------------------------|---------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| **group.id**                                | Según la tabla 11                                                         | Define el grupo y sus offsets.                                                 |
| **key.deserializer**                        | StringDeserializer                                                        | Claves textuales.                                                              |
| **value.deserializer**                      | ErrorHandlingDeserializer sobre deserializador JSON con tipo destino fijo | Un JSON inválido no detiene el contenedor; se deriva al DLT.                   |
| **enable.auto.commit**                      | false                                                                     | El contenedor confirma el offset tras procesar cada registro (AckMode RECORD). |
| **auto.offset.reset**                       | earliest o latest                                                         | Punto de inicio de un grupo sin offsets previos.                               |
| **max.poll.records / max.poll.interval.ms** | 50 / 300000                                                               | Lotes acotados y margen para reintentos sin expulsión del grupo.               |
| **partition.assignment.strategy**           | CooperativeStickyAssignor                                                 | Reequilibrios incrementales.                                                   |
| **concurrency**                             | 3 (agregador), 1 (monitor y vista)                                        | Un consumidor por partición en el grupo que concentra la carga.                |

Tabla 12. Propiedades de los consumidores Kafka.

# 9. Manejo de errores en el procesamiento de eventos

El objetivo del manejo de errores es que un mensaje defectuoso o una falla transitoria no detenga el consumo de una partición ni produzca efectos duplicados. Cada contenedor de listeners utiliza DefaultErrorHandler con un DeadLetterPublishingRecoverer, que publica el registro fallido en el tópico .DLT correspondiente, en la misma partición, e incorpora encabezados con el tópico, la partición y el offset originales, el grupo de consumidores de origen, la clase y el mensaje de la excepción. Como el agregador y el monitor leen el mismo tópico, un mensaje defectuoso genera una copia en el DLT por cada grupo que falla; ambas se distinguen por el encabezado kafka_dlt-original-consumer-group.

| **Tipo de error**                    | **Ejemplo**                                                             | **Tratamiento**                                                                | **Destino**            |
|--------------------------------------|-------------------------------------------------------------------------|--------------------------------------------------------------------------------|------------------------|
| **Deserialización**                  | JSON mal formado o tipo incompatible                                    | ErrorHandlingDeserializer lo convierte en error del registro; no se reintenta. | DLT inmediato          |
| **Contrato inválido**                | schemaVersion distinto de 1, cantidades o importes fuera de rango       | Excepción de contrato clasificada como no reintentable.                        | DLT inmediato          |
| **Transitorio**                      | Base de datos no disponible, tiempo de espera del productor de métricas | Backoff exponencial: 1 s, luego 2 s; hasta tres intentos en total.             | DLT al agotar intentos |
| **Duplicado**                        | Reentrega o republicación del mismo eventId                             | No es error: se registra CONSUME_DUPLICATE y se confirma el offset.            | Sin destino            |
| **Broker no disponible (productor)** | Orders no obtiene confirmación acks=all                                 | El evento permanece en la outbox y se reintenta cada cinco segundos.           | Outbox                 |

Tabla 13. Clasificación de errores y su tratamiento.

Los logs usan pares clave=valor para facilitar su búsqueda: CONSUME_OK, CONSUME_RETRY, CONSUME_DLT y CONSUME_DUPLICATE incluyen eventId, grupo, tópico, partición, offset, intento y un código de error, sin el payload completo ni datos de identidad. Los DLT no tienen consumidores automáticos: su contenido se inspecciona en Kafka UI o con kafka-admin-service y su reprocesamiento es una decisión operativa, para no repetir en bucle un error que requiere corrección.

# 10. Microservicio administrador de Kafka

kafka-admin-service expone una API REST de administración sobre AdminClient de Kafka. Sigue el patrón de rabbit-admin-service: escucha solo en 127.0.0.1:8187, exige JWT con rol Admin y scope Orders.Read, valida las solicitudes con Bean Validation y responde errores como ProblemDetails. Para proteger los flujos de negocio, la creación y la eliminación se restringen a tópicos con prefijo pedidos360.lab., y la modificación de configuraciones acepta solo una lista blanca de parámetros.

| **Método y ruta (/api/v1/admin/kafka)** | **Operación**                                                             | **Restricciones**                                                                |
|-----------------------------------------|---------------------------------------------------------------------------|----------------------------------------------------------------------------------|
| **GET /cluster**                        | Identificador del clúster, brokers y controlador                          | Solo lectura                                                                     |
| **GET /topics**                         | Lista de tópicos con particiones y réplicas                               | Excluye internos salvo parámetro explícito                                       |
| **GET /topics/{name}**                  | Particiones, líder, réplicas, ISR y configuración efectiva                | Solo lectura                                                                     |
| **POST /topics**                        | Crea un tópico con particiones, réplicas y configuraciones                | Prefijo pedidos360.lab.; particiones 1–12; réplicas 1–3                          |
| **PATCH /topics/{name}/configs**        | Modifica configuraciones con incrementalAlterConfigs                      | retention.ms, cleanup.policy, min.insync.replicas, segment.ms, max.message.bytes |
| **POST /topics/{name}/partitions**      | Aumenta el número de particiones                                          | Solo aumento; prefijo pedidos360.lab.                                            |
| **DELETE /topics/{name}**               | Elimina un tópico                                                         | Prefijo pedidos360.lab.; tópicos de negocio responden 409                        |
| **GET /consumer-groups**                | Grupos con estado y número de miembros                                    | Solo lectura                                                                     |
| **GET /consumer-groups/{groupId}**      | Miembros, asignación, offset confirmado, offset final y lag por partición | Solo lectura                                                                     |

Tabla 14. Operaciones de kafka-admin-service.

Los códigos de respuesta son 201 al crear, 200 al consultar o modificar, 204 al eliminar, 400 ante parámetros inválidos (incluida la creación de un tópico fuera del prefijo pedidos360.lab.), 401 sin token válido, 403 sin rol o scope, 404 ante recursos inexistentes, 409 ante tópicos existentes o protegidos (negocio, DLT o internos) y 503 si el clúster no responde. La modificación de configuraciones se admite en tópicos de laboratorio y de negocio, con valores acotados, y se rechaza en los tópicos internos. El contrato se documenta en contracts/kafka-admin-openapi.yaml. Como complemento replicable, scripts/ep5-kafka.sh ejecuta las mismas tareas de infraestructura con las herramientas kafka-topics, kafka-configs y kafka-consumer-groups dentro del contenedor del broker.

# 11. Kafka UI y supervisión operacional

Kafka UI se configura con el clúster pedidos360 y los tres brokers como bootstrap interno. Sus vistas cubren la operación diaria: Brokers muestra los nodos activos, el controlador y la distribución de particiones y líderes; Topics muestra particiones, factor de replicación, ISR, configuración y tamaño; Messages permite examinar mensajes por partición y offset, con su clave, encabezados y contenido; Consumers muestra los grupos, sus miembros, la asignación de particiones y el lag.

| **Métrica**                         | **Significado**                                      | **Uso operacional**                                                             |
|-------------------------------------|------------------------------------------------------|---------------------------------------------------------------------------------|
| **Log-end offset**                  | Posición del último mensaje escrito en una partición | Indica el volumen producido y su distribución entre particiones.                |
| **Offset confirmado**               | Última posición procesada y confirmada por un grupo  | Indica el avance de cada grupo de forma independiente.                          |
| **Lag**                             | Diferencia entre log-end offset y offset confirmado  | Un lag creciente y sostenido revela un consumidor lento o detenido.             |
| **Distribución del consumo**        | Partición asignada a cada miembro del grupo          | Confirma el balanceo; un miembro sin particiones indica exceso de consumidores. |
| **ISR y particiones subreplicadas** | Réplicas sincronizadas por partición                 | Un ISR menor a 3 anticipa un broker caído o atrasado.                           |
| **Mensajes en DLT**                 | Registros derivados por error                        | Su crecimiento señala un problema de contrato o de dependencia.                 |

Tabla 15. Métricas supervisadas y su interpretación.

La misma información se obtiene por línea de comandos con kafka-consumer-groups --describe, que informa por partición el offset actual, el offset final, el lag y el consumidor asignado, y mediante GET /consumer-groups/{groupId} de kafka-admin-service. Disponer de las tres vías permite verificar los datos de la interfaz y automatizar comprobaciones.

# 12. Integración con la SPA y API Gateway

La SPA incorpora la vista protegida “Ventas en vivo”, que reutiliza las clases visuales existentes y consulta GET /api/v1/ventas/en-vivo cada tres segundos mientras la vista está abierta. Se eligió consulta periódica en lugar de Server-Sent Events porque la integración de API Gateway HTTP cierra las conexiones al alcanzar su tiempo máximo de 30 segundos. La vista presenta, para el día UTC en curso, unidades, pedidos e importe por producto y moneda, junto con las alertas recientes y la hora de la última actualización.

API Gateway incorpora la ruta GET /api/v1/ventas/en-vivo con el mismo autorizador JWT de las siete rutas existentes; el BFF la reenvía a sales-stream-service, que vuelve a validar el token y exige Orders.Read. La información es agregada por tenant y no contiene datos de propietarios, por lo que es accesible para el rol User. La latencia esperada entre el registro de un pedido y su aparición en la vista es de pocos segundos (relay de un segundo, procesamiento y consulta de tres segundos); se describe como cuasi tiempo real y no como una medición de rendimiento. En la evidencia E-09, el procesamiento por Kafka, desde la confirmación del pedido hasta la actualización de la vista en el servidor, tomó 0,94 s; el resto del tiempo percibido corresponde al intervalo de consulta de la SPA.

# 13. Despliegue en AWS

## 13.1. Infraestructura y dimensionamiento

La solución se desplegó completa en una nueva cuenta de AWS Academy Learner Lab, ya que la cuenta utilizada en EP4 agotó sus créditos. La infraestructura se recreó con scripts/aws_deploy.py (etapas network, database, compute y gateway) y un journal propio que registra cada operación de escritura. Se creó la instancia i-01bcf3ef9d3a64d4e de tipo t3.large (2 vCPU, 8 GiB), el tamaño máximo admitido para EC2 en el laboratorio, con Ubuntu 24.04 LTS, disco gp3 de 30 GiB cifrado, IMDSv2 obligatorio y el perfil LabInstanceProfile. Se agrega un archivo de intercambio de 2 GiB como margen ante picos de memoria.

La red pedidos360-vpc (10.36.0.0/16) tiene una subred pública que solo contiene la EC2 y dos subredes privadas sin ruta a Internet para RDS, el ALB interno y el VPC Link. La instancia no tiene par de claves ni reglas de entrada salvo el puerto 8180 desde el ALB; la operación se realiza exclusivamente con AWS Systems Manager, lo que reemplaza la regla SSH temporal de EP4. Su salida se limita a HTTPS: las fuentes de apt se configuran con https://archive.ubuntu.com y https://security.ubuntu.com. RDS MySQL 8.4.11 (db.t3.micro) es privado, exige TLS y aloja los esquemas pedidos360_catalog, pedidos360_orders y pedidos360_streams con usuarios separados de aplicación y migración. La única entrada pública es la HTTP API az3h2vqgsi, con un límite de 10 solicitudes por segundo y ráfagas de 20.

| **Componente**                                                                      | **Unidades** | **Límite por unidad**           | **Subtotal máximo** |
|-------------------------------------------------------------------------------------|--------------|---------------------------------|---------------------|
| **Servicios Spring de mayor carga (bff, catalog, orders, sales-stream)**            | 4            | -Xmx256m (≈ 400 MiB de proceso) | ≈ 1,6 GiB           |
| **Servicios Spring de menor carga (receipts, rabbit-admin, insights, kafka-admin)** | 4            | -Xmx192m (≈ 320 MiB de proceso) | ≈ 1,3 GiB           |
| **Nodos RabbitMQ (EP4)**                                                            | 2            | Configuración existente         | ≈ 0,6 GiB           |
| **Nodos ZooKeeper**                                                                 | 3            | mem_limit 320 MiB               | 0,94 GiB            |
| **Brokers Kafka**                                                                   | 3            | mem_limit 896 MiB               | 2,63 GiB            |
| **Kafka UI**                                                                        | 1            | mem_limit 448 MiB               | 0,44 GiB            |
| **Sistema operativo y Docker**                                                      | —            | Estimado                        | ≈ 0,5 GiB           |

Tabla 16. Presupuesto de memoria en la instancia t3.large (valores de diseño).

La suma de límites máximos se aproxima a la memoria disponible; en operación normal los procesos no alcanzan simultáneamente su límite y el intercambio absorbe picos. El consumo se verifica en la evidencia E-19. Para no agotar los créditos de CPU de la instancia burstable, los servicios se inician de forma escalonada mediante dependencias de systemd.

## 13.2. Secuencia de despliegue

1.  Crear la red, la base de datos, la instancia y la integración de API Gateway con scripts/aws_deploy.py, incluida la ruta GET /api/v1/ventas/en-vivo.

2.  Compilar y probar los dos repositorios y empaquetar el release con su manifiesto SHA-256.

3.  Transferir el release por Systems Manager y ejecutar deploy/ep5-install.py, instalador idempotente que prepara intercambio y Docker, crea el esquema pedidos360_streams, levanta RabbitMQ, Kafka y Kafka UI e instala los ocho servicios como unidades systemd escalonadas.

4.  Verificar el estado de EC2, RDS, ALB y VPC Link, la entrega de la SPA en /app/ y las respuestas 401 de las rutas protegidas.

5.  Agregar en Entra ID la URI de redirección de la nueva API conservando las existentes.

6.  Ejecutar las evidencias de la sección 15.

Las credenciales de bases de datos y de Kafka UI se mantienen fuera del repositorio, en archivos de entorno con permisos restringidos, y no se imprimen en logs ni evidencias.

# 14. Casos de uso de streaming

| **Caso de uso**                              | **Necesidad**                                              | **Tópico y grupo**                      | **Configuración que lo resuelve**                                               |
|----------------------------------------------|------------------------------------------------------------|-----------------------------------------|---------------------------------------------------------------------------------|
| **Ventas por producto en cuasi tiempo real** | Conocer unidades e importe por producto durante el día     | orders.registered.v1 → sales-aggregator | Tres particiones y tres consumidores para paralelismo; acks=all e idempotencia. |
| **Alertas de pedidos relevantes**            | Detectar pedidos de alto valor sin afectar otros procesos  | orders.registered.v1 → order-monitor    | Grupo independiente con offsets propios; inicio latest.                         |
| **Estado actual reconstruible**              | Recuperar la vista tras un reinicio sin otra base de datos | product-metrics.v1 → sales-dashboard    | Compactación: se conserva el último valor por clave y se relee desde el inicio. |
| **Reprocesamiento de eventos recientes**     | Incorporar un nuevo consumidor o corregir un cálculo       | orders.registered.v1                    | Retención de 7 días; un grupo nuevo puede leer desde earliest.                  |
| **Diagnóstico de mensajes defectuosos**      | Aislar errores sin bloquear particiones                    | Tópicos .DLT                            | Retención de 14 días y encabezados de origen y excepción.                       |

Tabla 17. Casos de uso y configuración de Kafka asociada.

# 15. Pruebas y evidencias

## 15.1. Pruebas automatizadas

Las pruebas se organizan en tres niveles. Las pruebas unitarias cubren la validación de OrderRegisteredStreamV1 y ProductSalesMetricV1, SalesAggregationService, OrderAlertPolicy y LiveSalesView sin infraestructura. Las pruebas de integración con Testcontainers levantan Kafka y MySQL efímeros para verificar la publicación desde la outbox, el consumo por los tres grupos, la derivación al DLT de payloads inválidos, el tratamiento de duplicados y la reconstrucción de la vista desde el tópico compactado. Las pruebas de kafka-admin-service verifican autorización, validación, restricciones de prefijo y códigos HTTP. En el frontend se agregan pruebas de la vista “Ventas en vivo”. Las 41 pruebas existentes de EP3 y EP4 se mantienen y siguen aprobando.

## 15.2. Formato de las evidencias

Por indicación docente, las evidencias se registran como texto. Cada una identifica su objetivo, el indicador de la pauta al que responde, el entorno, el procedimiento con los comandos o vistas utilizados y el resultado. Las salidas se describen sin secretos ni tokens.

**Evidencia E-01. Arquitectura Kafka levantada con Docker Compose**

<table>
<colgroup>
<col style="width: 20%" />
<col style="width: 79%" />
</colgroup>
<tbody>
<tr class="odd">
<td><strong>Objetivo</strong></td>
<td>Comprobar que los tres nodos ZooKeeper y los tres brokers se ejecutan en la instancia EC2.</td>
</tr>
<tr class="even">
<td><strong>Indicador asociado</strong></td>
<td>EP5: Compose Kafka con ZooKeeper y brokers. EP6: docker-compose en la nube; arquitectura Kafka (10 %).</td>
</tr>
<tr class="odd">
<td><strong>Entorno</strong></td>
<td>AWS, EC2 i-01bcf3ef9d3a64d4e (t3.large), sesión SSM.</td>
</tr>
<tr class="even">
<td><strong>Procedimiento</strong></td>
<td><p>docker compose -f compose.kafka.yaml up -d --wait</p>
<p>docker compose -f compose.kafka.yaml ps</p></td>
</tr>
<tr class="odd">
<td><strong>Resultado</strong></td>
<td>Seis contenedores (zookeeper-1..3, kafka-1..3) en estado running y healthy.</td>
</tr>
</tbody>
</table>

**Evidencia E-02. Ensamble ZooKeeper con líder y seguidores**

<table>
<colgroup>
<col style="width: 20%" />
<col style="width: 79%" />
</colgroup>
<tbody>
<tr class="odd">
<td><strong>Objetivo</strong></td>
<td>Demostrar que los tres nodos forman un ensamble con quórum.</td>
</tr>
<tr class="even">
<td><strong>Indicador asociado</strong></td>
<td>EP6: arquitectura Kafka (10 %).</td>
</tr>
<tr class="odd">
<td><strong>Entorno</strong></td>
<td>AWS, EC2.</td>
</tr>
<tr class="even">
<td><strong>Procedimiento</strong></td>
<td><p>bash scripts/ep5-kafka.sh zk-status</p>
<p>El script consulta el comando srvr en cada nodo.</p></td>
</tr>
<tr class="odd">
<td><strong>Resultado</strong></td>
<td>Un nodo en modo leader y dos en modo follower.</td>
</tr>
</tbody>
</table>

**Evidencia E-03. Brokers registrados y controlador**

<table>
<colgroup>
<col style="width: 20%" />
<col style="width: 79%" />
</colgroup>
<tbody>
<tr class="odd">
<td><strong>Objetivo</strong></td>
<td>Comprobar el registro de los tres brokers y la existencia de un controlador.</td>
</tr>
<tr class="even">
<td><strong>Indicador asociado</strong></td>
<td>EP6: arquitectura Kafka (10 %); Kafka UI (5 %).</td>
</tr>
<tr class="odd">
<td><strong>Entorno</strong></td>
<td>AWS, EC2 y Kafka UI mediante reenvío de puertos SSM.</td>
</tr>
<tr class="even">
<td><strong>Procedimiento</strong></td>
<td><p>docker exec -e KAFKA_HEAP_OPTS=-Xmx128m kafka-1 zookeeper-shell zookeeper-1:2181 ls /brokers/ids</p>
<p>Kafka UI → Brokers.</p></td>
</tr>
<tr class="odd">
<td><strong>Resultado</strong></td>
<td>Lista [1, 2, 3]; Kafka UI muestra tres brokers en línea y uno marcado como controlador.</td>
</tr>
</tbody>
</table>

**Evidencia E-04. Kafka UI levantado y conectado**

<table>
<colgroup>
<col style="width: 20%" />
<col style="width: 79%" />
</colgroup>
<tbody>
<tr class="odd">
<td><strong>Objetivo</strong></td>
<td>Comprobar que Kafka UI se ejecuta con su Compose propio y administra el clúster.</td>
</tr>
<tr class="even">
<td><strong>Indicador asociado</strong></td>
<td>EP5: Compose de Kafka UI. EP6: Kafka UI (5 %).</td>
</tr>
<tr class="odd">
<td><strong>Entorno</strong></td>
<td>AWS, EC2; navegador local con reenvío de puertos al 127.0.0.1:8090 de la instancia.</td>
</tr>
<tr class="even">
<td><strong>Procedimiento</strong></td>
<td><p>docker compose -f compose.kafka-ui.yaml up -d --wait</p>
<p>Iniciar sesión en Kafka UI y abrir el clúster pedidos360.</p></td>
</tr>
<tr class="odd">
<td><strong>Resultado</strong></td>
<td>Contenedor kafka-ui healthy; clúster pedidos360 en línea con tres brokers y los tópicos de la sección 5.</td>
</tr>
</tbody>
</table>

**Evidencia E-05. Dos tópicos con tres particiones y tres réplicas**

<table>
<colgroup>
<col style="width: 20%" />
<col style="width: 79%" />
</colgroup>
<tbody>
<tr class="odd">
<td><strong>Objetivo</strong></td>
<td>Verificar particiones, réplicas, líderes e ISR de los tópicos de negocio.</td>
</tr>
<tr class="even">
<td><strong>Indicador asociado</strong></td>
<td>EP6: dos tópicos 3×3 en Kafka UI; justificación de tópicos (10 %).</td>
</tr>
<tr class="odd">
<td><strong>Entorno</strong></td>
<td>AWS, EC2 y Kafka UI.</td>
</tr>
<tr class="even">
<td><strong>Procedimiento</strong></td>
<td><p>docker exec -e KAFKA_HEAP_OPTS=-Xmx128m kafka-1 kafka-topics --bootstrap-server kafka-1:29092 \</p>
<p>--describe --topic pedidos360.orders.registered.v1</p>
<p>Repetir con pedidos360.sales.product-metrics.v1; Kafka UI → Topics.</p></td>
</tr>
<tr class="odd">
<td><strong>Resultado</strong></td>
<td>PartitionCount: 3 y ReplicationFactor: 3 en ambos; un líder distinto por partición; ISR con tres réplicas.</td>
</tr>
</tbody>
</table>

**Evidencia E-06. Parámetros de administración de tópicos**

<table>
<colgroup>
<col style="width: 20%" />
<col style="width: 79%" />
</colgroup>
<tbody>
<tr class="odd">
<td><strong>Objetivo</strong></td>
<td>Comprobar retención, política de limpieza y réplicas mínimas por flujo.</td>
</tr>
<tr class="even">
<td><strong>Indicador asociado</strong></td>
<td>EP5: parámetros de tópicos (12 %). EP6: administración de Kafka (15 %).</td>
</tr>
<tr class="odd">
<td><strong>Entorno</strong></td>
<td>AWS, EC2.</td>
</tr>
<tr class="even">
<td><strong>Procedimiento</strong></td>
<td><p>docker exec -e KAFKA_HEAP_OPTS=-Xmx128m kafka-1 kafka-configs --bootstrap-server kafka-1:29092 \</p>
<p>--entity-type topics --entity-name &lt;tópico&gt; --describe</p></td>
</tr>
<tr class="odd">
<td><strong>Resultado</strong></td>
<td>orders.registered.v1: cleanup.policy=delete, retention.ms=604800000, min.insync.replicas=2. product-metrics.v1: cleanup.policy=compact, min.insync.replicas=2. DLT: retention.ms=1209600000.</td>
</tr>
</tbody>
</table>

**Evidencia E-07. Publicación de un pedido en Kafka desde Orders**

<table>
<colgroup>
<col style="width: 20%" />
<col style="width: 79%" />
</colgroup>
<tbody>
<tr class="odd">
<td><strong>Objetivo</strong></td>
<td>Trazar un pedido desde la SPA hasta su mensaje en el tópico.</td>
</tr>
<tr class="even">
<td><strong>Indicador asociado</strong></td>
<td>EP5: productores (14 %). EP6: flujo de producción y consumo (12 %); diseño de eventos (6 %).</td>
</tr>
<tr class="odd">
<td><strong>Entorno</strong></td>
<td>AWS; SPA en /app/ con sesión institucional de Microsoft Entra.</td>
</tr>
<tr class="even">
<td><strong>Procedimiento</strong></td>
<td><p>Registrar un pedido multítem en la SPA.</p>
<p>Consultar order_stream_outbox por orderId y el log de orders-service (PUBLISH_CONFIRMED).</p>
<p>Kafka UI → Messages del tópico, filtrando por la clave orderId.</p></td>
</tr>
<tr class="odd">
<td><strong>Resultado</strong></td>
<td>HTTP 201; fila con published_at no nulo; log con tópico, partición y offset; mensaje con clave orderId y payload OrderRegisteredStreamV1 con sus líneas.</td>
</tr>
</tbody>
</table>

**Evidencia E-08. Grupos de consumidores y distribución de particiones**

<table>
<colgroup>
<col style="width: 20%" />
<col style="width: 79%" />
</colgroup>
<tbody>
<tr class="odd">
<td><strong>Objetivo</strong></td>
<td>Mostrar los tres grupos, su asignación de particiones, offsets y lag.</td>
</tr>
<tr class="even">
<td><strong>Indicador asociado</strong></td>
<td>EP5: consumidores (14 %); consumer groups (12 %). EP6: métricas de offsets y lag (15 %).</td>
</tr>
<tr class="odd">
<td><strong>Entorno</strong></td>
<td>AWS, EC2 y Kafka UI → Consumers.</td>
</tr>
<tr class="even">
<td><strong>Procedimiento</strong></td>
<td><p>docker exec -e KAFKA_HEAP_OPTS=-Xmx128m kafka-1 kafka-consumer-groups --bootstrap-server kafka-1:29092 \</p>
<p>--describe --group pedidos360-sales-aggregator</p>
<p>Repetir con pedidos360-order-monitor y pedidos360-sales-dashboard.</p></td>
</tr>
<tr class="odd">
<td><strong>Resultado</strong></td>
<td>Agregador con tres miembros y una partición cada uno; monitor y vista con un miembro y tres particiones; lag 0 en reposo.</td>
</tr>
</tbody>
</table>

**Evidencia E-09. Reacción del sistema en cuasi tiempo real**

<table>
<colgroup>
<col style="width: 20%" />
<col style="width: 79%" />
</colgroup>
<tbody>
<tr class="odd">
<td><strong>Objetivo</strong></td>
<td>Demostrar que un nuevo pedido actualiza la vista y genera procesos derivados sin intervención.</td>
</tr>
<tr class="even">
<td><strong>Indicador asociado</strong></td>
<td>EP6: respuesta a eventos en tiempo real (12 %); casos de uso (15 %).</td>
</tr>
<tr class="odd">
<td><strong>Entorno</strong></td>
<td>AWS; SPA con la vista “Ventas en vivo” abierta.</td>
</tr>
<tr class="even">
<td><strong>Procedimiento</strong></td>
<td><p>Registrar un pedido con total igual o superior a 50.000 CLP.</p>
<p>Observar la vista y el tópico product-metrics.v1 en Kafka UI.</p>
<p>Revisar el log de sales-stream-service (ORDER_ALERT).</p></td>
</tr>
<tr class="odd">
<td><strong>Resultado</strong></td>
<td>En pocos segundos aumentan unidades, pedidos e importe de los productos; la métrica publicada incrementa version; aparece una alerta de alto valor.</td>
</tr>
</tbody>
</table>

**Evidencia E-10. Lag y recuperación de un consumidor detenido**

<table>
<colgroup>
<col style="width: 20%" />
<col style="width: 79%" />
</colgroup>
<tbody>
<tr class="odd">
<td><strong>Objetivo</strong></td>
<td>Mostrar cómo el lag permite detectar un problema operacional y su resolución.</td>
</tr>
<tr class="even">
<td><strong>Indicador asociado</strong></td>
<td>EP6: métricas de offsets y lag (15 %); administración de Kafka (15 %).</td>
</tr>
<tr class="odd">
<td><strong>Entorno</strong></td>
<td>AWS, EC2 y Kafka UI.</td>
</tr>
<tr class="even">
<td><strong>Procedimiento</strong></td>
<td><p>Detener sales-stream-service con systemctl.</p>
<p>Registrar dos pedidos y consultar el grupo pedidos360-sales-aggregator.</p>
<p>Iniciar el servicio y volver a consultar.</p></td>
</tr>
<tr class="odd">
<td><strong>Resultado</strong></td>
<td>Con el servicio detenido, el grupo no tiene miembros y el lag total es 2. Tras el inicio, el lag vuelve a 0 y cada pedido se contabiliza una sola vez.</td>
</tr>
</tbody>
</table>

**Evidencia E-11. Payload inválido derivado al DLT sin bloquear la partición**

<table>
<colgroup>
<col style="width: 20%" />
<col style="width: 79%" />
</colgroup>
<tbody>
<tr class="odd">
<td><strong>Objetivo</strong></td>
<td>Comprobar el tratamiento de mensajes defectuosos.</td>
</tr>
<tr class="even">
<td><strong>Indicador asociado</strong></td>
<td>EP5: manejo de errores (12 %).</td>
</tr>
<tr class="odd">
<td><strong>Entorno</strong></td>
<td>AWS, EC2.</td>
</tr>
<tr class="even">
<td><strong>Procedimiento</strong></td>
<td><p>docker exec -i -e KAFKA_HEAP_OPTS=-Xmx128m kafka-1 kafka-console-producer --bootstrap-server kafka-1:29092 \</p>
<p>--topic pedidos360.orders.registered.v1 --property parse.key=true --property key.separator="|"</p>
<p>Enviar una clave con un JSON inválido y luego registrar un pedido válido.</p></td>
</tr>
<tr class="odd">
<td><strong>Resultado</strong></td>
<td>Log CONSUME_DLT sin reintentos; mensaje en pedidos360.orders.registered.v1.DLT con encabezados de tópico, partición, offset y excepción; el pedido válido posterior se procesa con normalidad.</td>
</tr>
</tbody>
</table>

**Evidencia E-12. Idempotencia ante un evento duplicado**

<table>
<colgroup>
<col style="width: 20%" />
<col style="width: 79%" />
</colgroup>
<tbody>
<tr class="odd">
<td><strong>Objetivo</strong></td>
<td>Comprobar que una reentrega no duplica acumulados.</td>
</tr>
<tr class="even">
<td><strong>Indicador asociado</strong></td>
<td>EP5: manejo de errores (12 %); consumidores (14 %).</td>
</tr>
<tr class="odd">
<td><strong>Entorno</strong></td>
<td>AWS, EC2.</td>
</tr>
<tr class="even">
<td><strong>Procedimiento</strong></td>
<td><p>Republicar en el tópico el payload de un evento ya procesado, con la misma clave.</p>
<p>Consultar el log y la vista en vivo.</p></td>
</tr>
<tr class="odd">
<td><strong>Resultado</strong></td>
<td>Log CONSUME_DUPLICATE con el eventId; los acumulados no cambian.</td>
</tr>
</tbody>
</table>

**Evidencia E-13. Tolerancia a la caída de un broker**

<table>
<colgroup>
<col style="width: 20%" />
<col style="width: 79%" />
</colgroup>
<tbody>
<tr class="odd">
<td><strong>Objetivo</strong></td>
<td>Verificar la continuidad del servicio con un broker detenido.</td>
</tr>
<tr class="even">
<td><strong>Indicador asociado</strong></td>
<td>EP6: arquitectura Kafka (10 %); justificación de réplicas (10 %).</td>
</tr>
<tr class="odd">
<td><strong>Entorno</strong></td>
<td>AWS, EC2.</td>
</tr>
<tr class="even">
<td><strong>Procedimiento</strong></td>
<td><p>docker stop kafka-2</p>
<p>Describir los tópicos, registrar un pedido y comprobar su procesamiento.</p>
<p>docker start kafka-2</p></td>
</tr>
<tr class="odd">
<td><strong>Resultado</strong></td>
<td>Las particiones lideradas por el broker 2 cambian de líder; ISR de dos réplicas; el pedido se publica y procesa. Tras el inicio, el ISR vuelve a tres réplicas.</td>
</tr>
</tbody>
</table>

**Evidencia E-14. Operaciones del microservicio administrador**

<table>
<colgroup>
<col style="width: 20%" />
<col style="width: 79%" />
</colgroup>
<tbody>
<tr class="odd">
<td><strong>Objetivo</strong></td>
<td>Ejercitar la administración de tópicos, configuraciones y grupos.</td>
</tr>
<tr class="even">
<td><strong>Indicador asociado</strong></td>
<td>EP5: administrador Kafka (6 %); administración de tópicos y grupos (6 %).</td>
</tr>
<tr class="odd">
<td><strong>Entorno</strong></td>
<td>Local, con el fixture Admin (JWT con rol Admin y Orders.Read) sobre el clúster de tres brokers.</td>
</tr>
<tr class="even">
<td><strong>Procedimiento</strong></td>
<td><p>POST /topics (pedidos360.lab.demo), GET /topics/{name}, PATCH /topics/{name}/configs (retention.ms), POST /topics/{name}/partitions, DELETE /topics/{name}.</p>
<p>DELETE sobre un tópico de negocio; cualquier operación con token de rol User y sin token.</p>
<p>GET /consumer-groups/pedidos360-sales-aggregator.</p></td>
</tr>
<tr class="odd">
<td><strong>Resultado</strong></td>
<td>201, 200, 200, 200 y 204 en la secuencia; 409 para el tópico de negocio; 403 para el rol User; 401 sin token; detalle de grupo con offsets y lag por partición.</td>
</tr>
</tbody>
</table>

**Evidencia E-15. Reconstrucción de la vista desde el tópico compactado**

<table>
<colgroup>
<col style="width: 20%" />
<col style="width: 79%" />
</colgroup>
<tbody>
<tr class="odd">
<td><strong>Objetivo</strong></td>
<td>Demostrar el uso de la compactación para recuperar estado.</td>
</tr>
<tr class="even">
<td><strong>Indicador asociado</strong></td>
<td>EP6: administración de Kafka (15 %); casos de uso (15 %).</td>
</tr>
<tr class="odd">
<td><strong>Entorno</strong></td>
<td>AWS, EC2 y SPA.</td>
</tr>
<tr class="even">
<td><strong>Procedimiento</strong></td>
<td><p>Anotar los acumulados mostrados en la vista.</p>
<p>Reiniciar sales-stream-service.</p>
<p>Consultar nuevamente la vista.</p></td>
</tr>
<tr class="odd">
<td><strong>Resultado</strong></td>
<td>Tras el reinicio, el grupo de la vista relee product-metrics.v1 desde el inicio y presenta los mismos acumulados.</td>
</tr>
</tbody>
</table>

**Evidencia E-16. Integración RabbitMQ sin cambios**

<table>
<colgroup>
<col style="width: 20%" />
<col style="width: 79%" />
</colgroup>
<tbody>
<tr class="odd">
<td><strong>Objetivo</strong></td>
<td>Comprobar que el mismo pedido sigue procesándose por RabbitMQ.</td>
</tr>
<tr class="even">
<td><strong>Indicador asociado</strong></td>
<td>EP5 y EP6: Kafka complementa la arquitectura sin afectar RabbitMQ; dos nodos, tres colas con DLQ, exchanges direct y topic.</td>
</tr>
<tr class="odd">
<td><strong>Entorno</strong></td>
<td>AWS, EC2 y consola de RabbitMQ.</td>
</tr>
<tr class="even">
<td><strong>Procedimiento</strong></td>
<td><p>Para el pedido de E-07, revisar los logs de receipts-service y order-insights-service.</p>
<p>Consultar el clúster, las colas, sus DLQ y los exchanges.</p></td>
</tr>
<tr class="odd">
<td><strong>Resultado</strong></td>
<td>Comprobante, auditoría y resumen con ACK; clúster de dos nodos sin particiones; tres colas con sus DLQ; exchanges direct y topic enlazados.</td>
</tr>
</tbody>
</table>

**Evidencia E-17. API Gateway y validación JWT de la nueva ruta**

<table>
<colgroup>
<col style="width: 20%" />
<col style="width: 79%" />
</colgroup>
<tbody>
<tr class="odd">
<td><strong>Objetivo</strong></td>
<td>Comprobar la protección de GET /api/v1/ventas/en-vivo.</td>
</tr>
<tr class="even">
<td><strong>Indicador asociado</strong></td>
<td>EP6: API Manager valida JWT; frontend consume a través del API Manager; OAuth 2.0/OIDC.</td>
</tr>
<tr class="odd">
<td><strong>Entorno</strong></td>
<td>AWS, API Gateway az3h2vqgsi (https://az3h2vqgsi.execute-api.us-east-1.amazonaws.com/app/).</td>
</tr>
<tr class="even">
<td><strong>Procedimiento</strong></td>
<td><p>Solicitar la ruta sin token y con un bearer inválido.</p>
<p>Abrir la vista desde la SPA con sesión institucional y revisar la solicitud en las herramientas del navegador.</p></td>
</tr>
<tr class="odd">
<td><strong>Resultado</strong></td>
<td>HTTP 401 en los dos primeros casos; HTTP 200 con token válido emitido por Entra ID mediante authorization code con PKCE.</td>
</tr>
</tbody>
</table>

**Evidencia E-18. Pruebas automatizadas**

<table>
<colgroup>
<col style="width: 20%" />
<col style="width: 79%" />
</colgroup>
<tbody>
<tr class="odd">
<td><strong>Objetivo</strong></td>
<td>Registrar el resultado de las pruebas de backend y frontend.</td>
</tr>
<tr class="even">
<td><strong>Indicador asociado</strong></td>
<td>EP5: el código compila, sigue buenas prácticas y responde a pruebas básicas.</td>
</tr>
<tr class="odd">
<td><strong>Entorno</strong></td>
<td>Local, CachyOS (Arch Linux), Java 25, Node 26 y Testcontainers.</td>
</tr>
<tr class="even">
<td><strong>Procedimiento</strong></td>
<td><p>bash mvnw clean verify</p>
<p>npm ci &amp;&amp; npm test &amp;&amp; npm run build</p></td>
</tr>
<tr class="odd">
<td><strong>Resultado</strong></td>
<td>Build exitoso: 82 pruebas Java y 20 pruebas React aprueban sin fallos, errores ni omisiones, y la compilación de producción del frontend finaliza correctamente.</td>
</tr>
</tbody>
</table>

**Evidencia E-19. Uso de memoria en la instancia t3.large**

<table>
<colgroup>
<col style="width: 20%" />
<col style="width: 79%" />
</colgroup>
<tbody>
<tr class="odd">
<td><strong>Objetivo</strong></td>
<td>Contrastar el presupuesto de memoria con el consumo real.</td>
</tr>
<tr class="even">
<td><strong>Indicador asociado</strong></td>
<td>Dimensionamiento de la sección 13.</td>
</tr>
<tr class="odd">
<td><strong>Entorno</strong></td>
<td>AWS, EC2 con todos los servicios activos.</td>
</tr>
<tr class="even">
<td><strong>Procedimiento</strong></td>
<td><p>free -m</p>
<p>docker stats --no-stream</p>
<p>systemctl show -p MemoryCurrent,MemoryPeak pedidos360-*</p></td>
</tr>
<tr class="odd">
<td><strong>Resultado</strong></td>
<td>Unos 2.981 MiB disponibles y 0 B de intercambio en uso; todos los contenedores bajo su mem_limit (el más cercano, Kafka UI, al 75 %); los cuatro servicios de mayor carga suman 1.134 MiB y los cuatro de menor carga 713 MiB; las 11 unidades systemd activas.</td>
</tr>
</tbody>
</table>

# 16. Limitaciones y trabajo pendiente

- Los tres brokers, los tres nodos ZooKeeper y los dos nodos RabbitMQ comparten un mismo host: la replicación protege frente a la caída de un contenedor, no frente a la pérdida de la instancia. No se declara alta disponibilidad.

- El modo ZooKeeper fue retirado en Apache Kafka 4.0. Se utiliza por requerimiento de la evaluación; una evolución natural es migrar a KRaft.

- El tráfico entre servicios y brokers dentro del host no usa TLS ni SASL; la exposición se limita a loopback y a la red Docker.

- Las alertas se conservan en memoria y se pierden al reiniciar el servicio; su persistencia queda como trabajo futuro.

- La vista usa consulta periódica cada tres segundos y no notificaciones push; la latencia observada no constituye una medición de rendimiento.

- El reprocesamiento de mensajes en DLT es manual.

- Se mantienen las limitaciones declaradas en EP3 y EP4: no se ha verificado un inicio de sesión real con rol Admin con respuesta HTTP 200 ni la expiración natural de tokens, y la autorización Admin de los administradores se prueba con el fixture local.

- La instancia t3.large conserva unos 2,9 GiB disponibles con todos los servicios activos; incorporar nuevos servicios requeriría separar la plataforma Kafka en otra instancia.

- El laboratorio no permite crear roles IAM, por lo que la instancia usa el perfil LabInstanceProfile, con permisos más amplios que los mínimos necesarios.

- La imagen de RabbitMQ usa el UID 999, que en el host coincide con el usuario de sistema del BFF. Los montajes de los contenedores impiden el acceso cruzado a datos, pero la separación de UID o el uso de userns-remap queda como mejora.

- npm audit informa cuatro vulnerabilidades en dependencias del frontend (dos moderadas y dos altas), que no se trataron en esta etapa para no alterar MSAL ni Vite antes de la entrega.

# 17. Trazabilidad con las pautas EP5 y EP6

| **Indicador EP5**                                      | **Peso** | **Secciones** | **Evidencias**   |
|--------------------------------------------------------|----------|---------------|------------------|
| **Configuración del cliente Kafka**                    | 12 %     | 7.3, 8.5      | E-07, E-08       |
| **Productores y consumidores con ambos tópicos y DTO** | 12 %     | 6, 7, 8       | E-07, E-09       |
| **Microservicio administrador de Kafka**               | 6 %      | 10            | E-14             |
| **Productores con DTO y serializadores**               | 14 %     | 6, 7          | E-07             |
| **Consumidores con @KafkaListener y lógica separada**  | 14 %     | 8             | E-08, E-09, E-12 |
| **Manejo de errores**                                  | 12 %     | 9             | E-11, E-12       |
| **Parámetros de administración de tópicos**            | 12 %     | 5.2, 5.6      | E-06             |
| **Consumer groups**                                    | 12 %     | 8.1           | E-08, E-10       |
| **Operaciones de administración de tópicos y grupos**  | 6 %      | 5.6, 10       | E-14, E-08       |

Tabla 18. Correspondencia con los indicadores de EP5.

| **Indicador EP6**                                                | **Peso** | **Secciones** | **Evidencias**         |
|------------------------------------------------------------------|----------|---------------|------------------------|
| **Arquitectura Kafka: ZooKeeper, brokers y tolerancia a fallos** | 10 %     | 4             | E-01, E-02, E-03, E-13 |
| **Justificación de dos tópicos 3×3**                             | 10 %     | 5.3, 5.4      | E-05, E-13             |
| **Uso de Kafka UI**                                              | 5 %      | 11            | E-04, E-05             |
| **Flujo de producción y consumo**                                | 12 %     | 3, 7, 8       | E-07, E-08             |
| **Diseño de los eventos**                                        | 6 %      | 6             | E-07                   |
| **Reacción en tiempo real**                                      | 12 %     | 8.4, 12       | E-09                   |
| **Administración: particiones, réplicas, retención y grupos**    | 15 %     | 5, 8, 10      | E-06, E-10, E-15       |
| **Supervisión de offsets, lag y distribución**                   | 15 %     | 11            | E-08, E-10             |
| **Casos de uso de streaming**                                    | 15 %     | 14            | E-09, E-15             |

Tabla 19. Correspondencia con los indicadores de EP6.

Los elementos de presentación que provienen de etapas anteriores, como la instancia de API Gateway, la validación de JWT, el tenant de Entra ID con sus usuarios, el despliegue del frontend y el backend, y la topología RabbitMQ de dos nodos con tres colas y sus DLQ, se demuestran con la infraestructura de EP4 y se verifican nuevamente en las evidencias E-16 y E-17.

# 18. Fuentes y reproducibilidad

Repositorios documentados: github.com/chashmdai/pedidos360-backend y github.com/chashmdai/pedidos360-frontend. Los archivos principales de esta etapa son compose.kafka.yaml, compose.kafka-ui.yaml, kafka-support/src/main/resources/pedidos-kafka.properties, los módulos sales-stream-service y kafka-admin-service, la migración V3\_\_order_stream_outbox.sql de orders-service, los contratos contracts/order-registered-stream-v1.schema.json, contracts/product-sales-metric-v1.schema.json, contracts/kafka-admin-openapi.yaml y contracts/live-sales-response-v1.schema.json, el instalador deploy/ep5-install.py, la configuración de destino config/aws-target.json y los scripts scripts/ep5-kafka.sh y scripts/ep5-entra-redirect.py. Las decisiones de implementación se registran en docs/EP5_DECISIONES.md y las salidas de las evidencias en docs/evidence/ep5/.

Comandos de referencia: bash scripts/ep5-kafka.sh up; bash scripts/ep5-kafka.sh ui up; bash scripts/ep5-kafka.sh topics describe; bash scripts/ep5-kafka.sh groups describe; bash mvnw clean verify.

Referencias técnicas: documentación de Apache Kafka 3.9 (diseño, replicación y configuración de brokers, tópicos, productores y consumidores); documentación de Confluent Platform 7.9 y aviso de fin de soporte de ZooKeeper en Confluent Platform (support.confluent.io), que establece la versión 7.9.x como la última que incluye ZooKeeper; documentación de Spring for Apache Kafka (contenedores de listeners, DefaultErrorHandler y DeadLetterPublishingRecoverer); documentación de Kafbat UI (ui.docs.kafbat.io); y restricciones de servicio de AWS Academy Learner Lab, que admite instancias EC2 de tamaño nano a large.
