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

## Pendientes conocidos para la Fase 4 (no resueltos todavía)

- `aws_deploy.py`, `entra_config.py` y `config/aws-public.json` fijan la cuenta `002996184293`
  y el journal `docs/evidence/phase5/`; el despliegue en la cuenta nueva usará un journal nuevo.
- `aws_deploy.py` compute: AMI, `ClientToken`, tipo `t3.medium` y disco de 20 GiB deben
  ajustarse a t3.large y ≥ 30 GiB.
- `deploy/ep4-install.py` presupone los `.env` creados por `deploy/install-release.py` (fase 5):
  en la cuenta nueva hay que encadenar ambos instaladores antes del instalador EP5.
- `npm audit` informa 4 vulnerabilidades (2 moderadas, 2 altas) en dependencias del frontend;
  por indicación del usuario no se tratan en esta iteración.
