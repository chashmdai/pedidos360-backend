# Pedidos360: evolución técnica EP4

Este documento complementa la EP3; no la reemplaza. Conservo el PDF, capturas e historial anteriores. React está autorizado por el docente. No preparo material de exposición.

## Qué cambié

Partí de Orders con outbox transaccional, el exchange direct y el consumidor Receipts ya verificados. Añadí un exchange topic enlazado al direct y dos proyecciones independientes en `order-insights-service`: auditoría de pedidos y resumen diario de importes solicitados por moneda. El resumen no representa pagos ni una reserva de existencias. Cada consumidor guarda eventos únicos de forma atómica antes de confirmar, por lo que una redelivery no incrementa dos veces los importes.

La configuración común sigue en `messaging-support/src/main/resources/pedidos-rabbit.properties`; `InsightsTopology` declara los nuevos beans Queue, Exchange y Binding. No añadí un common-domain ni cambié `OrderRegisteredV1`, el agregado Order, sus snapshots ni el contrato REST de creación.

| Flujo | Exchange / binding principal | Cola | DLQ |
|---|---|---|---|
| Comprobantes | direct `pedidos360.orders.events.v1` / `order.registered.v1` | `pedidos360.receipts.order-registered.v1` | `pedidos360.receipts.failed.v1` |
| Auditoría | topic `pedidos360.orders.insights.v1` / `order.registered.*` | `pedidos360.audit.order-registered.v1` | `pedidos360.audit.failed.v1` |
| Resumen diario UTC | mismo topic / `*.registered.v1` | `pedidos360.sales.order-registered.v1` | `pedidos360.sales.failed.v1` |

El binding entre el direct y el topic usa `order.registered.v1`. El publisher de la outbox sigue realizando una publicación persistente confirmada. Los confirms no son ACK del consumidor: confirmo el efecto persistente de cada proyección antes de su ACK manual. Un contrato inválido o conflicto permanente recibe NACK sin requeue; una IOException se reintenta hasta tres veces y después pasa a la DLQ. Un fallo de transporte al confirmar se propaga para permitir redelivery.

## Clúster y persistencia

Utilizo dos nodos RabbitMQ 4.2.9 fijados por digest, Compose y volúmenes propios. El broker EP3 local conserva su volumen y procesos. Los puertos EP4 5674/5675 y 15674/15675 se ligan a 127.0.0.1; Erlang distribution queda dentro de la red Docker. La cookie y las contraseñas están fuera de Git.

Las seis colas son classic durables con mensajes persistentes. Sus mensajes **no se replican** entre nodos. Dos nodos comparten metadatos y enrutan tráfico entre sí, pero no equivalen a HA. En AWS ambos residen en la EC2 existente, por lo que tampoco tolero pérdida del host. Una parada/reinicio conservando volúmenes es una prueba distinta de failover o pérdida permanente de un nodo. No ejecuto reset, force_boot ni prune.

El productor cloud intenta primero el segundo nodo; los consumidores intentan primero el primero. Las direcciones alternativas facilitan reconexión, sin prometer disponibilidad de una cola cuyo único nodo esté caído. El bootstrap declara la topología con el administrador; los usuarios runtime tienen permisos de publicación o consumo sobre los recursos correspondientes y no crean/eliminan recursos.

## Administrador

Mantengo las rutas REST anteriores y el servicio dedicado `RabbitAdminService`. Añadí `PATCH /api/v1/rabbit/queues/{name}/policy` para modificar TTL y longitud máxima mediante una política cuyo patrón coincide con una única cola de laboratorio. No elimino/recreo una cola para simular actualización. Rechazo argumentos de declaración que tienen precedencia sobre la política con 409 y valido rangos, nombres, tipos y configuraciones vacías. Estas políticas tienen las consecuencias normales de TTL/longitud máxima; solo las aplico a recursos descartables `pedidos360.lab.*`, nunca a colas de negocio.

Los endpoints siguen exigiendo JWT válido, rol Admin y Orders.Read. La eliminación mantiene las condiciones broker-side if-empty/if-unused. Los tests administrativos crean y retiran exclusivamente sus propios recursos aislados.

## Cloud y seguridad

Reutilizo EC2 i-0818fdfafcfb7cb31, RDS pedidos360-mysql, ALB interno, VPC Link y HTTP API 7k2zyh0t0d en us-east-1. No amplié instancia, disco ni RDS, ni creé un servicio cloud facturable adicional. Mantengo los costos de uso/tráfico y almacenamiento de los recursos existentes. Instalo Docker en la EC2 propia sin actualizar toda la distribución.

La SPA compilada se aloja en EC2 y se sirve por el BFF a través del mismo Gateway HTTPS en `/app/`. Las dos rutas GET públicas de archivos son independientes de las siete rutas API, que conservan authorizer JWT y scopes. No utilizo localhost como prueba de hosting cloud. React solo cambia su ruta base y las URI de MSAL; conservo el diseño y el comportamiento anterior.

Después del checkpoint autorizado añadí exclusivamente `https://7k2zyh0t0d.execute-api.us-east-1.amazonaws.com/app/` a la aplicación SPA existente. La lectura Graph posterior confirmó que no cambiaron roles, permisos ni scopes y se conservaron las URI locales. El tenant es institucional y preexistente; no afirmo haberlo creado para esta evaluación. Los usuarios y asignaciones se comprueban mediante Graph sin elevar privilegios ni capturar tokens.

La transferencia utiliza SSH por túnel SSM con clave de host fijada, sin abrir SSH público. Los ficheros privados de RDS existentes permanecen en EC2; no los copio al repositorio ni los sustituyo. Guardo hashes por fila de los datos iniciales para comprobar su conservación.

## Pruebas ejecutadas hasta la preparación del despliegue

- Java: `bash scripts/ep4-build.sh backend` ejecuta `mvnw ... clean verify`. 39 pruebas, incluidas las anteriores con MySQL real, rollback de outbox, tests HTTP de seguridad, administración y clúster de dos nodos Testcontainers. Resultado en `evidence/ep4/backend-verify.txt`.
- React: `bash scripts/ep4-build.sh frontend`. 11 pruebas y build de producción con ruta `/app/`; `evidence/ep4/frontend-tests.txt` y `frontend-build.txt`.
- Compose WSL: dos nodos unidos y saludables, tres colas y tres DLQ. Esta comprobación es **local**, no acredita Docker en AWS.
- Inspección real AWS y SSM: infraestructura existente saludable, datos iniciales (2 productos, 2 pedidos, 3 líneas), Docker instalado, sin ampliación de capacidad. `evidence/ep4/aws-inventory-before.json`, `instance-inspection.json`, `host-preparation.json`.
- Graph: configuración y usuarios existentes, scopes canónicos y URI autorizada añadida. `evidence/ep4/entra-directory.json`, `entra-spa-before.json`, `entra-spa-after.json`.

Después ejecuté y registré por separado las pruebas del despliegue cloud y del navegador; se detallan abajo. No considero ejecutada una comprobación por disponer de un script.

## Resultado ejecutado en AWS y con identidad institucional

Desplegué el release `ep4-20261021T094446Z`, con seis servicios saludables y dos nodos Compose. Comprobé los hashes de los JAR en EC2 y los bytes HTML/JS/CSS recibidos por Gateway. Las conexiones finales muestran productor en el nodo 2 y consumidores en el nodo 1: hubo tráfico entre nodos, no dos brokers independientes. Quedaron aproximadamente 1,6 GiB de memoria disponibles, sin aumentar la EC2.

Comprobé el rechazo sin JWT/inválido (401) y los HTTP 200/201 institucionales en los logs reales del Gateway. Desde la SPA alojada en AWS inicié sesión con intervención manual, consulté catálogo, comprobé los tres scopes y el rol User, solicité renovación, recibí 403 en administración y cerré sesión. Después, `/app/catalogo` redirigió al inicio sin sesión. No extraje access tokens, cookies ni almacenamiento MSAL.

Creé el pedido `cee13d49-4bd2-43be-bc85-7c700b3d37a5` con dos líneas por 30.970 CLP. Su evento `77bc410d-3462-4982-a428-ab4b83c305b6` quedó confirmado y produjo tres archivos y tres ACK. Republiqué el mismo payload: recibí DUPLICATE/ACK en los tres consumidores y no cambió ningún archivo ni conteo.

Detuve únicamente ambos nodos EP4. La SPA pudo registrar el pedido `b07ddc47-8ec0-4e9f-974c-76ef85b07727` por 21.980 CLP; observé su outbox pendiente tras ocho intentos. Después de recuperar los mismos contenedores/volúmenes con Compose, quedó publicada en el intento doce y se generaron los tres efectos con ACK. Los cinco mensajes diagnósticos de las DLQ permanecieron (auditoría 2, comprobantes 1, resumen 2) y se conservaron los tres archivos previos.

La verificación final MySQL confirmó TLS_AES_256_GCM_SHA384 con VERIFY_IDENTITY, transporte seguro obligatorio, migración V2 de outbox y usuarios app sin DDL. Los hashes por fila del catálogo y pedidos iniciales no cambiaron: quedaron 2 productos, 4 pedidos y 7 líneas, tras añadir solamente los dos pedidos de esta prueba. No modifiqué reglas SG ni asociaciones/rutas previas, incluidas las predeterminadas/ajenas; el inventario final compara sus valores sin depender del orden de las listas AWS.

La pasada HTTP posterior del nuevo servicio añadió dos pruebas a las 39 del clean verify: **41 Java distintas**, 11 React y build aprobados. No sumo dos veces las doce pruebas repetidas del módulo Insights. Los HTTP 200 administrativos y los fallos IOException se probaron con fixture local; no los atribuyo a una sesión Admin real en AWS.

Evidencia: [trazabilidad completa](EP4_TRAZABILIDAD.md), [estado final AWS](evidence/ep4/aws-final-verification.json), [pedido y ACK](evidence/ep4/cloud-order-verification.json), [duplicados](evidence/ep4/cloud-idempotency.json), [recuperación](evidence/ep4/cloud-recovery.json), [pedido recuperado](evidence/ep4/cloud-recovered-order.json), [Entra real](evidence/ep4/entra-browser.json), [HTTP Gateway](evidence/ep4/gateway-access-logs.json).

## Reproducción desde WSL codex

```bash
bash scripts/ep4-toolchain.sh
bash scripts/ep4-build.sh all
python3 scripts/ep4-broker.py up
bash scripts/ep4.sh inspect
```

El entorno AWS usa `ep4-env.sh` con la CLI Linux instalada en el HOME y el archivo de credenciales ya administrado por el operador; no copia sus valores. Al reiniciar el laboratorio, renuevo credenciales manualmente y compruebo STS antes de continuar. El inventario reconoce los nuevos identificadores del journal EP4 y conserva el journal histórico.

`ep4-prepare-release.py` empaqueta JAR, frontend y archivos revisados con hashes. La transferencia por `ep4.sh transfer` usa únicamente el host reconciliado. Antes de ejecutar `ep4-install-release.py`, verifico los hashes y el estado de cualquier instalación interrumpida. El instalador conserva el release anterior y copias privadas de las unidades/entornos para recuperación. Nunca lo uso para borrar recursos del laboratorio.

## Límites que mantengo explícitos

- No hay HA, replicación de colas classic ni protección contra pérdida permanente de la EC2/volumen.
- Las proyecciones usan un único escritor por directorio y crecen por evento. El resumen recorre esos archivos; no es un almacén analítico para alto volumen.
- Los confirms/mandatory detectan publicación no confirmada o sin ruta; no prueban por sí solos que estén presentes todos los bindings esperados. La verificación de topología y los efectos de los tres consumidores son evidencias adicionales.
- La outbox no rellena retrospectivamente los pedidos anteriores al despliegue de mensajería. Conservo esos pedidos.
- No sustituyo pruebas institucionales por tokens fixture ni me atribuyo una nota de la rúbrica.
