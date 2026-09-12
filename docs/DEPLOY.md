# Ejecución local y estado del despliegue

FASE 2 y FASE 3 verifican el runtime local en WSL2. FASE 5 desplegó EC2, RDS y API Gateway después del checkpoint aprobado. La instalación fue reconciliada tras un reinicio del laboratorio y verificada: tres servicios UP, ALB healthy, MySQL con TLS y migraciones correctas. La evidencia end-to-end de usuario se registra por separado en FASE 6.

**Estado al cerrar la entrega:** el usuario informó que AWS está apagado. FASE 7 usa las evidencias fechadas ya obtenidas; no se realizaron consultas ni pruebas AWS posteriores a ese aviso. Los estados healthy/available que aparecen en los informes son observaciones previas, no una afirmación de disponibilidad actual. No se infiere que los recursos hayan sido eliminados.

Para una sesión nueva del laboratorio, consultar la guía operativa [ARRANQUE_LABORATORIO.md](ARRANQUE_LABORATORIO.md), que comienza con la renovación de las tres credenciales temporales y evita repetir etapas de creación.

## Entorno local reproducible

Mantener los dos repositorios como carpetas hermanas y una terminal WSL abierta. Desde `pedidos360-backend`, con Java 25, Maven Linux, Node 24 y Docker Linux:

```bash
bash scripts/setup-local.sh
bash scripts/mysql.sh up -d --wait
mvn clean verify
(cd ../pedidos360-frontend && npm ci && npm test)
python3 scripts/entra_config.py frontend npm run build
bash scripts/dev.sh start entra
bash scripts/dev.sh status
python3 scripts/verify-entra-runtime.py
python3 scripts/verify-database.py
```

`setup-local.sh` conserva secretos existentes y genera los que faltan fuera del repositorio. El volumen MySQL conserva los datos. No ejecutar el arranque sobre procesos Pedidos360 ya iniciados: comprobar `status` y, si corresponde reconstruir, usar `bash scripts/dev.sh stop`, construir y volver a iniciar. Este stop no detiene Docker.

| Componente | Dirección local |
|---|---|
| Frontend | http://localhost:5173 |
| BFF | http://127.0.0.1:8180 |
| Catalog | http://127.0.0.1:8181 |
| Orders | http://127.0.0.1:8182 |
| MySQL Docker | 127.0.0.1:13306 |

Los tres procesos Java publican `/actuator/health`; sus endpoints de negocio exigen access token. Las URLs/IDs de Entra se derivan de `config/entra-public.json`. No ejecutar las solicitudes históricas de `docs/entra-checkpoint/` para arrancar o probar: los registros ya existen.

MySQL tiene nombres y datos propios de Pedidos360. Los scripts no usan contenedores, redes ni volúmenes de otros proyectos. No utilizar prune ni limpieza global. Logs y registros de los procesos: `~/.local/state/pedidos360-phase1/run/`; los logs HTTP omiten headers, queries y cuerpos.

## Demostración local de seguridad

Iniciar sesión en la SPA, abrir Mi sesión, comprobar User y scopes. Consultar Catálogo, crear pedido y recuperarlo en Mis pedidos. User recibe 403 al comprobar Admin. Renovar sesión solicita un token a Microsoft; cerrar sesión debe volver al inicio y proteger las rutas. No asignar roles ni modificar Entra para repetir la demostración normal.

Para la matriz automatizada controlada, detener los procesos propios, usar `start local`, ejecutar `python3 scripts/verify-local.py` y restaurar `start entra` después de detener el modo local. El fixture no se despliega ni acredita identidad Microsoft. Cada ejecución crea un pedido de prueba; no elimina datos.

## AWS desplegado y reanudación

Cuenta `002996184293`, rol `voclabs`, región `us-east-1`. Plan y costos aprobados en [AWS_CHECKPOINT.md](AWS_CHECKPOINT.md). IDs y respuestas reales: [journal](evidence/phase5/deployment-journal.json). No ejecutar de nuevo las escrituras para arrancar el laboratorio.

Ruta: SPA localhost → HTTPS HTTP API → VPC Link → ALB interno → BFF EC2 → Catalog/Orders loopback → RDS privado. API real: `https://7k2zyh0t0d.execute-api.us-east-1.amazonaws.com/api/v1`. EC2 `i-0818fdfafcfb7cb31`, RDS `pedidos360-mysql`. No hay NAT, EIP, hosting frontend ni dominio propio.

Para usar AWS desde la SPA, mantener una terminal WSL abierta y ejecutar únicamente el frontend:

```bash
bash scripts/dev.sh status
# Si hay procesos Pedidos360 locales registrados, detenerlos primero con dev.sh stop.
python3 scripts/entra_config.py frontend-cloud npm test
python3 scripts/entra_config.py frontend-cloud npm run build
bash scripts/dev.sh start cloud
python3 scripts/verify-cloud-http.py
```

El modo `cloud` no inicia Java local ni requiere credenciales de MySQL local. Lee IDs Entra de `config/entra-public.json` y endpoint AWS de `config/aws-public.json`. El diseño visual se conserva.

Después de renovar credenciales, ejecutar primero STS. Desde WSL se puede indicar `AWS_CLI` con la ruta real al `aws.exe` Windows autenticado; el script usa archivos de solicitud temporales 0600 fuera del repositorio y no copia credenciales AWS a Linux:

```bash
export AWS_CLI=/mnt/c/Users/Benja/AppData/Local/Programs/Amazon/AWSCLIV2/aws.exe
"$AWS_CLI" sts get-caller-identity --region us-east-1 --no-cli-pager
python3 scripts/reconcile-aws.py
python3 scripts/aws_deploy.py status
```

Estos dos scripts verifican cuenta/rol y consultan los IDs existentes. Un reinicio puede cambiar la IP pública; la SPA sigue usando Gateway. No cambiar el endpoint por una IP ni recrear EC2. Ante un recurso ausente, error de permisos o escritura incierta, inspeccionar y conservar el journal; no borrar su entrada para forzar un reintento. El error inicial de longitud de contraseña se reconcilió con DBInstanceNotFound y conserva su historial.

`aws_deploy.py` contiene las etapas aprobadas `network`, `database`, `compute`, `gateway`; ya se ejecutaron y no son comandos de arranque. Cada escritura se registra antes del despacho. Los recursos predeterminados, vockey y roles/políticas del laboratorio permanecen fuera del alcance. LabInstanceProfile se asocia únicamente a la EC2 nueva.

## Release y administración

Build en WSL; tres JAR independientes. `prepare-aws-release.py` prepara una carpeta privada fuera de Git con SHA-256, manifest público y secretos nuevos. La transferencia inicial se hizo por SSH /32 con clave exclusiva y clave del host comprobada por SSM. Ese ingreso SSH ya está cerrado. SSM ejecutó inspección, reparación y verificación; no requiere copiar credenciales AWS a EC2 ni instalar el plugin de sesión para Run Command.

En EC2: `/opt/pedidos360/runtime` (Temurin 25 fijado y checksum verificado), `/opt/pedidos360/releases/<release>`, enlace `current`, tres unidades `pedidos360-bff`, `pedidos360-catalog`, `pedidos360-orders`. JAR y carpetas de release son legibles por los usuarios de servicio; secretos permanecen root-only en `/etc/pedidos360/*.env`. BFF no recibe contraseñas DB. Los logs `/var/log/pedidos360/<context>` contienen método/ruta/estado/duración sin bearer, cuerpos ni query.

`deploy/install-release.py` instala una release nueva. Para una interrupción, ejecutar primero la inspección de `deploy/inspect-instance.py` mediante SSM en la instancia registrada. Si los hashes/unidades/configuración ya están correctos, reanudar solo el paso pendiente. `deploy/verify-runtime.py` verifica lo instalado sin repetir provisión ni reiniciar servicios. La primera reanudación corrigió únicamente la carpeta 0700 → 0755 y arrancó las unidades existentes; ver [evidencia](evidence/phase5/ssm-resume-release-permissions.json).

RDS usa `VERIFY_IDENTITY`, hostname real y CA oficial en un truststore de Connector/J; se conservan los CA públicos normales de Java para Entra. Dos esquemas, cuatro usuarios aislados, Flyway con credenciales propias y pools 5/1. Los dos productos de ejemplo se habilitan explícitamente en `cloud`; no se importa la base local. Evidencia de TLS, MySQL 8.4.11, migraciones y denegaciones 1142: [runtime-verification.json](evidence/phase5/runtime-verification.json).

Un rollback de código puede cambiar `current` a una release anterior conservada y reiniciar solo esas unidades, después de revisar compatibilidad de las migraciones. No se revierte la base automáticamente. La limpieza de RDS/datos/snapshots requiere una decisión explícita; detener el laboratorio no equivale a eliminar todos los recursos ni a detener todos los costos.
