# Checkpoint AWS EP5 (cuenta 647660738152, us-east-1)

Estado: **aprobado por el usuario el 2026-11-19** (con apt solo por HTTPS y throttling 10/20). El preflight de solo lectura del 2026-11-19
(`docs/evidence/ep5/aws/preflight-names.json`) confirma que la cuenta no tiene recursos de Pedidos360:
solo la VPC por defecto y el par `vockey`, que no se usa. Es una cuenta nueva: todo se crea desde cero
con un journal nuevo (`docs/evidence/ep5/aws/deployment-journal.json`); el journal de EP4 es histórico.

## Recursos que se crearán

| Etapa | Recurso | Nombre | Configuración |
|---|---|---|---|
| network | VPC | `pedidos360-vpc` | 10.36.0.0/16, DNS support + hostnames |
| network | Subred pública | `pedidos360-public-b` | 10.36.0.0/24, us-east-1b (solo EC2) |
| network | Subredes privadas | `pedidos360-private-b`, `pedidos360-private-c` | 10.36.10.0/24 (1b), 10.36.20.0/24 (1c); sin ruta a Internet |
| network | Internet Gateway | `pedidos360-igw` | adjunto a la VPC; ruta 0.0.0.0/0 solo en `pedidos360-public-rt` |
| network | Tablas de rutas | `pedidos360-public-rt`, `pedidos360-private-rt` | pública → IGW; privada solo `local` |
| network | Security groups | `pedidos360-vpclink-sg`, `-alb-sg`, `-app-sg`, `-db-sg` | regla de salida por defecto **eliminada**; reglas en la tabla de seguridad |
| database | DB subnet group | `pedidos360-db-subnets` | private-b + private-c |
| database | Parameter group | `pedidos360-mysql84` | familia mysql8.4, `require_secure_transport=1` |
| database | RDS | `pedidos360-mysql` | **db.t3.micro**, MySQL **8.4.11**, gp3 **20 GiB** cifrado, Single-AZ us-east-1b, **no pública**, backup 1 día, deletion protection, sin upgrade automático, sin Performance Insights |
| compute | EC2 | `pedidos360-app` | **t3.large** (2 vCPU, 8 GiB), AMI **`ami-0719278fd447e399f`** (Ubuntu 24.04 LTS, Canonical 099720109477, `ubuntu-noble-24.04-amd64-server-20261118`), raíz **gp3 30 GiB cifrado**, `LabInstanceProfile`, IMDSv2 obligatorio, créditos *standard* (sin cargos por ráfaga), IPv4 pública automática (sin EIP), **sin par de claves**, user data `deploy/ec2-bootstrap.sh` |
| gateway | ALB interno | `pedidos360-internal-alb` | scheme internal, private-b/c, listener HTTP:80 → TG `pedidos360-bff-tg` (HTTP 8180, health `/actuator/health`) |
| gateway | VPC Link | `pedidos360-vpclink` | private-b/c, `vpclink-sg` |
| gateway | HTTP API | `pedidos360-http-api` | autorizador JWT `pedidos360-entra-jwt` (issuer `https://login.microsoftonline.com/72fd0b5a-…/v2.0`, audience `114f7b58-…`); integración HTTP_PROXY por VPC Link; stage `$default` auto-deploy, throttling **10 rps / ráfaga 20** (EP4: 5/10) |
| gateway | Log group | `/pedidos360/api-gateway` | retención 7 días; formato sin token, query ni cuerpo |

Rutas del HTTP API: las 7 de EP4 + 1 de EP5 con JWT, y 2 GET públicas de archivos de la SPA.

| Ruta | Autorización |
|---|---|
| `GET /api/v1/productos`, `GET /api/v1/productos/{id}` | JWT, `Catalog.Read` |
| `GET /api/v1/pedidos`, `GET /api/v1/pedidos/{id}`, `GET /api/v1/admin/pedidos` | JWT, `Orders.Read` (admin exige además rol Admin en BFF y Orders) |
| `POST /api/v1/pedidos` | JWT, `Orders.Create` (BFF y Orders exigen además `Catalog.Read`) |
| `GET /api/v1/me` | JWT, cualquiera de los tres scopes |
| **`GET /api/v1/ventas/en-vivo`** | JWT, `Orders.Read` (EP5) |
| `GET /app`, `GET /app/{proxy+}` | pública: solo archivos estáticos de la SPA |

Dentro de la EC2 (no son recursos AWS): swap de 2 GiB, Docker, RabbitMQ EP4 (2 nodos), Kafka (3 ZooKeeper + 3 brokers),
Kafka UI y 8 servicios systemd con los heaps de la tabla 16.

## Revisión de seguridad

Security groups (todas las reglas por SG de origen o destino; ninguna entrada desde 0.0.0.0/0):

| SG | Entrada | Salida |
|---|---|---|
| `vpclink-sg` | — | TCP 80 → `alb-sg` |
| `alb-sg` | TCP 80 ← `vpclink-sg` | TCP 8180 → `app-sg` |
| `app-sg` (EC2) | TCP 8180 ← `alb-sg` (**sin 22, sin otros puertos**) | TCP 3306 → `db-sg`; TCP 443 → 0.0.0.0/0 |
| `db-sg` (RDS) | TCP 3306 ← `app-sg` | — |

- **Única regla hacia 0.0.0.0/0:** salida TCP 443 de la EC2. Es estrictamente necesaria sin NAT ni VPC endpoints: Session Manager/SSM, JWKS de Microsoft Entra, paquetes Ubuntu por HTTPS, Docker Hub (imágenes fijadas por digest), Temurin (verificado por SHA-256) y el bundle CA de RDS. Los VPC endpoints de SSM costarían más que toda la instancia, y Docker Hub y Entra los necesitarían igualmente.
- **Única entrada pública:** el HTTP API de API Gateway (HTTPS administrado). El ALB es interno y la EC2 no acepta nada de Internet aunque tenga IPv4 pública (la usa para salir).
- **RDS privado:** subredes sin ruta a Internet, `PubliclyAccessible=false`, solo desde `app-sg`, TLS obligatorio (`require_secure_transport`), clientes con `VERIFY_IDENTITY` y truststore de la CA oficial, almacenamiento cifrado, usuarios por contexto (`app`: DML; `migration`: DDL) con `REQUIRE SSL`.
- **Loopback:**
  - Catalog 8181, Orders 8182, Receipts 8183, Rabbit-admin 8184, Insights 8185, Sales-stream 8186 y Kafka-admin 8187 escuchan en `127.0.0.1`.
  - Kafka publica solo `127.0.0.1:19092/19093/19094`; ZooKeeper no se publica.
  - Kafka UI: `127.0.0.1:8090`. RabbitMQ: `127.0.0.1:5674/5675` (AMQP) y `15674/15675` (Management).
  - El BFF escucha en `0.0.0.0:8180`, alcanzable solo desde `alb-sg`.
  - El instalador **falla** si encuentra otro puerto fuera de loopback (aparte del BFF y de sshd, que no tiene regla de entrada).
- **Acceso operativo solo por SSM:**
  - Run Command para instalar e inspeccionar.
  - Session Manager con port forwarding para Kafka UI (8090), RabbitMQ Management (15674) y kafka-admin (8187).
  - La transferencia del release es SCP dentro de un túnel SSM hacia `127.0.0.1:22`, con clave propia de alcance restringido y clave de host fijada leída por SSM. No hay par de claves EC2 ni regla de entrada 22.
- **Secretos:**
  - Las contraseñas RDS están en `~/.config/pedidos360/aws-647660738152/` (0700/0600).
  - En la EC2 viven en `/etc/pedidos360/*.env` (0600 root). La copia transferida se borra al terminar la instalación.
  - RabbitMQ (cookie y usuarios) y Kafka UI generan sus secretos en la propia EC2.
  - Nada se imprime ni va a Git o evidencias.
- **Limitación declarada:** `LabInstanceProfile`/`LabRole` lo administra el laboratorio y tiene permisos amplios. El Learner Lab no permite crear un rol mínimo.

## Orden de ejecución y duración estimada

| # | Paso | Comando | Duración |
|---|---|---|---|
| 1 | Red | `python3 scripts/aws_deploy.py network` | ~1 min |
| 2 | Base de datos (RDS en segundo plano) | `python3 scripts/aws_deploy.py database` | 1 min + **10–15 min** hasta `available` |
| 3 | EC2 + bootstrap (JDK, CA RDS, SSM) | `python3 scripts/aws_deploy.py compute` | 5–8 min hasta SSM `Online` |
| 4 | ALB, VPC Link, HTTP API, rutas y stage | `python3 scripts/aws_deploy.py gateway` | 5–8 min (ALB y VPC Link `AVAILABLE`) |
| 5 | Build local + SPA para `/app/` con el endpoint nuevo | `bash scripts/ep5-build.sh` | 4–5 min (en paralelo con 2–4) |
| 6 | Release con manifiesto SHA-256 | `python3 scripts/ep5-release.py` | <1 min |
| 7 | Transferencia por SSM | `bash scripts/ep4.sh transfer setup / tunnel / upload` | 2–5 min (≈ 350 MB) |
| 8 | Instalación (swap, Docker, RDS, RabbitMQ, Kafka, UI, 8 servicios escalonados) | `python3 scripts/ep5-install-release.py` | 12–20 min |
| 9 | Verificación (status, health del target, 401 sin token por Gateway) | `python3 scripts/aws_deploy.py status` + sondas HTTP | 2–3 min |

Total: **~45–60 min**. Las etapas 2–4 y 5 se solapan. Si vencen las credenciales a mitad de camino, me detengo; el journal
registra cada escritura antes de ejecutarla y nunca reintenta a ciegas. La Fase 5 (URI de redirección en Entra) es un checkpoint aparte.

## Costo estimado (on-demand us-east-1, bajo tráfico)

| Recurso | USD/hora | USD/día |
|---|---|---|
| EC2 t3.large | 0,0832 | 2,00 |
| ALB interno (+ LCU mínimas) | 0,0225 + ~0,002 | ~0,58 |
| RDS db.t3.micro Single-AZ | 0,017 | 0,41 |
| IPv4 pública de la EC2 | 0,005 | 0,12 |
| EBS gp3 30 GiB | — | 0,08 |
| RDS gp3 20 GiB | — | 0,08 |
| HTTP API (1 USD/millón), VPC Link (sin costo en HTTP API), CloudWatch Logs, SSM | — | ~0,01–0,05 |
| **Total** | | **≈ 3,3 USD/día (≈ 23 USD por semana encendido)** |

Referencial, no es un límite de facturación. Si el laboratorio detiene la EC2 al cerrar la sesión, dejan de correr la EC2
y su IPv4; el ALB y RDS siguen (salvo que se detengan). No hay NAT Gateway, EIP, S3 ni CloudFront.
