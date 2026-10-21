# Pedidos360 backend

## EP4 - versión cloud verificada

Frontend desplegado: **https://7k2zyh0t0d.execute-api.us-east-1.amazonaws.com/app/**. La SPA se aloja en la EC2 propia y llega por HTTPS al Gateway, VPC Link, ALB interno y BFF existentes. Las siete rutas API conservan JWT/scopes. La disponibilidad depende de que el laboratorio esté encendido.

La iteración añade un clúster RabbitMQ real de dos nodos en Docker Compose sobre esa EC2, tres colas con tres DLQ y enrutamiento direct/topic. Mantiene Orders -> outbox -> Receipts y suma auditoría y resumen diario por moneda en `order-insights-service`. Son seis servicios Spring; las colas classic no replican mensajes y ambos nodos comparten host, por lo que **no es HA**.

**[PDF complementario EP4](docs/EP4_IMPLEMENTACION_EVIDENCIAS.pdf)** · [implementación](docs/EP4_IMPLEMENTACION.md) · [trazabilidad P01-P11/R1-R8](docs/EP4_TRAZABILIDAD.md) · [operación reproducible](docs/EP4_OPERACION.md) · [evidencias](docs/evidence/ep4/).

Pruebas: 39 Java en `clean verify` y 2 HTTP adicionales de Insights (41 distintas), 11 React y build de producción; AWS acreditó clúster, rutas, NACK/DLQ, tres efectos/ACK, duplicados, recuperación de outbox y conservación de datos. Entra real desde la SPA cloud: login, catálogo, pedidos, renovación, User 403 y logout. Los JAR desplegados y los bytes servidos de la SPA se contrastan por SHA-256. La evidencia EP3 permanece intacta.

## EP3 — RabbitMQ

En EP3 se incorporó el flujo local Orders → outbox transaccional → RabbitMQ → comprobante durable, junto con un microservicio administrador REST protegido. Su launcher habilita la mensajería con el perfil `ep3`; el despliegue EP4 la habilita mediante configuración explícita sin cambiar el contrato.

**Entregable principal: [PDF de implementación y evidencias EP3](docs/EP3_RABBITMQ_EVIDENCIAS.pdf)**, ocho páginas A4 revisadas visualmente. [Informe técnico, matriz y demo](docs/EP3_RABBITMQ_IMPLEMENTACION.md), [índice de capturas reales](docs/evidence/ep3/CAPTURAS_PENDIENTES.md) y [prueba Entra institucional](docs/evidence/ep3/entra-verification.json).

Ejecutar como usuario WSL `codex`. Con el MySQL Pedidos360 existente: `bash scripts/ep3-toolchain.sh`, `bash scripts/ep3.sh setup`, `bash scripts/ep3.sh broker up -d --wait`, `bash scripts/ep3.sh configure-broker`, `bash scripts/ep3-build.sh all` y `bash scripts/ep3.sh start entra`. Detener primero procesos EP3 propios con `bash scripts/ep3.sh stop` si ya están activos. La SPA usa localhost:5173 y los cinco servicios 19180–19184 para respetar puertos ajenos. El modo `local` sirve para aceptación controlada; no sustituye Entra. No hay operaciones AWS en este cierre.

Catálogo, pedidos multítem y BFF con Microsoft Entra, desplegados en EC2 y RDS detrás de API Gateway. Java 25, Spring Boot 4.1.1, Maven 3.9.16 y MySQL 8.4.11. Desarrollo, build, tests y frontend local se ejecutan en **WSL2**.

Para demostrar el backend AWS existente, ejecutar `bash scripts/dev.sh start cloud` y abrir `http://localhost:5173`. Este modo inicia únicamente la SPA con el endpoint Gateway verificado; consultar [DEPLOY.md](docs/DEPLOY.md) para reanudar el laboratorio sin recrear recursos.

[Entrega y evidencias históricas](docs/ENTREGA.md). El cierre anterior ocurrió con AWS apagado; las nuevas verificaciones cloud de EP4 están fechadas y separadas en `docs/evidence/ep4/`.

Para reanudar una nueva sesión del laboratorio, seguir [Arrancar Pedidos360 después de renovar AWS](docs/ARRANQUE_LABORATORIO.md). La guía cubre la actualización de las tres credenciales temporales, reconciliación, inicio condicional de EC2/RDS, health checks y arranque de la SPA.

## Arranque local

Mantener `pedidos360-backend` y `pedidos360-frontend` como carpetas hermanas. Los comandos siguientes se ejecutan desde este repositorio, en una terminal WSL con el toolchain Linux disponible:

```bash
bash scripts/setup-local.sh
bash scripts/mysql.sh up -d --wait
mvn clean verify
# Alternativa reproducible: bash mvnw clean verify
(cd ../pedidos360-frontend && npm ci && npm test)
python3 scripts/entra_config.py frontend npm run build
bash scripts/dev.sh start entra
python3 scripts/verify-database.py
```

Abrir `http://localhost:5173`, iniciar sesión con Microsoft, ir al catálogo y registrar un pedido. El launcher configura Entra desde `config/entra-public.json` e inicia Catalog (8181), Orders (8182), BFF (8180) y Vite (5173). En este modo no inicia el emisor JWT de pruebas. `Mi sesión` muestra únicamente claims verificados por el BFF, permite solicitar renovación MSAL y comprobar acceso Admin. Usa `127.0.0.1` y fuerza IPv4 en las JVM para permitir el reenvío localhost Windows–WSL. Se comprobó el acceso desde ambos entornos. Mantener una terminal WSL abierta durante la demostración.

```bash
bash scripts/dev.sh status
bash scripts/dev.sh stop
bash scripts/mysql.sh ps
```

`stop` solo señala los procesos creados por el launcher y comprueba PID, comando y hora de inicio. No detiene Docker. Para reconstruir, detener primero los procesos Java propios, ejecutar el build y volver a arrancarlos. Logs y PIDs: `~/.local/state/pedidos360-phase1/run/`.

## Base de datos

`compose.yaml` crea exclusivamente `pedidos360-mysql`, `pedidos360-network` y `pedidos360-mysql-data`. Puerto host: **127.0.0.1:13306**. La imagen MySQL está fijada por versión y digest; no utiliza ningún contenedor, red ni volumen de otros proyectos.

| Contexto | Base | Usuario aplicación | Usuario migraciones |
|---|---|---|---|
| Catalog | pedidos360_catalog | pedidos360_catalog_app | pedidos360_catalog_migration |
| Orders | pedidos360_orders | pedidos360_orders_app | pedidos360_orders_migration |

Aplicación: SELECT/INSERT/UPDATE/DELETE únicamente sobre su base. Migrador: permisos de esquema sobre su base, sin permisos globales ni sobre el otro contexto. Flyway usa una conexión separada; Hibernate solo valida el esquema. Los tests usan MySQL efímero separado, nunca esta instancia de desarrollo.

El script genera cinco secretos aleatorios una sola vez en `~/.config/pedidos360/local/` y un `application.env`. No se almacenan en Git. El directorio tiene modo 0700; el archivo de entorno, 0600. Los archivos individuales montados por Compose tienen 0444 dentro de ese directorio privado para que el UID de MySQL pueda leerlos. No imprimir el archivo de entorno ni los secretos. Cambiar archivos de contraseña después de inicializar el volumen no rota automáticamente usuarios MySQL.

Inicialización de esquemas/usuarios: `docker/mysql/init-databases.sh`. Migraciones por servicio: `src/main/resources/db/migration`. Los perfiles de demostración `local`, `entra` y `cloud` añaden el seed de dos productos desde `db/local`; no se ejecuta en el perfil por defecto. Los fixtures no son datos productivos. RDS MySQL 8.4.11 está desplegado y verificado con TLS e identidad del servidor en us-east-1.

## Seguridad y alcance

Todos los endpoints de negocio validan JWT firmado, issuer, audience, tiempo de validez, identidad y scopes. Son públicos `/actuator/health` y los GET de archivos de la SPA bajo `/app/`; estos últimos no exponen datos de negocio. El BFF propaga el access token a URLs internas fijas, con timeouts y sin seguir redirecciones. Las rutas `/pedidos` usan `tid` + `oid` para filtrar por propietario. `/admin/pedidos` exige además rol Admin y Orders.Read, y consulta únicamente el tenant validado.

El emisor de `scripts/local-identity.mjs` es **un fixture de desarrollo**, sin contraseña ni identidad real; cualquier proceso local puede obtener su token demo. No se despliega ni acredita integración Entra. Usa claves locales fuera del repositorio y tokens de diez minutos. La configuración normal exige `JWT_ISSUER`, `JWT_AUDIENCE`, `JWT_JWKS_URI`, `JWT_TENANT_ID` y `JWT_CLIENT_ID`, derivados de los registros verificados. El launcher los inyecta desde la configuración pública. El modo fixture permanece restringido a localhost.

Scopes del contrato: `Catalog.Read`, `Orders.Read`, `Orders.Create`; crear exige también Catalog.Read para consultar snapshots. Los roles User/Admin se convierten en ROLE_User/ROLE_Admin. La consulta administrativa exige Admin; un User con todos los scopes recibe 403. Una firma válida no basta: cada API valida issuer, audience, tenant, azp de la SPA, versión 2.0 y exp obligatorio; Spring aplica vigencia/nbf con su tolerancia de reloj de 60 segundos.

Consultar [arquitectura](docs/ARQUITECTURA.md), [pruebas](docs/PRUEBAS.md), [decisiones](docs/DECISIONES.md), [ejecución y despliegue](docs/DEPLOY.md) y [OpenAPI](contracts/openapi.yaml). No se incorporan pagos, reservas, stock transaccional ni CRUD administrativo.

## Configuración y pruebas de identidad

Los identificadores de `config/entra-public.json` son públicos, no secretos. La SPA usa authorization code + PKCE, sessionStorage gestionado por MSAL y acquireTokenSilent con fallback interactivo. No requiere contraseña de aplicación, certificado ni permisos Microsoft Graph. Las asignaciones de aplicación son User para be.torrejons@duocuc.cl y Admin para ja.pissani@duocuc.cl. Estas no son funciones administrativas del tenant.

Para repetir la batería de 51 comprobaciones HTTP consolidada en FASE 3, detener antes el modo Entra y elegir explícitamente el modo local:

```bash
bash scripts/dev.sh stop
bash scripts/dev.sh start local
python3 scripts/verify-local.py
bash scripts/dev.sh stop
bash scripts/dev.sh start entra
```

Los JWT del fixture no son aceptados por los servicios en modo Entra. Las pruebas automatizadas con claves RSA de prueba y Testcontainers se documentan por separado de las pruebas de navegador con Microsoft en `docs/PRUEBAS.md` y los informes de fases del workspace.

FASE 4 fue aprobada y FASE 5 desplegó EC2, RDS privado y HTTP API con VPC Link/ALB interno. La instalación se reconcilió tras reiniciar el laboratorio y quedó saludable. Consultar [DEPLOY.md](docs/DEPLOY.md), [journal](docs/evidence/phase5/deployment-journal.json) y [pruebas cloud](docs/evidence/phase5/). Si las credenciales temporales vencen, solicitar renovación y reconciliar los mismos IDs antes de continuar.
