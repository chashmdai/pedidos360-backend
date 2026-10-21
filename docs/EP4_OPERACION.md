# Operación técnica EP4 desde WSL codex

La infraestructura ya existe. No ejecutar fases de creación de `aws_deploy.py`, no recrear RDS, no borrar volúmenes ni abrir Management/AMQP públicamente. La guía histórica de arranque conserva el detalle para renovar manualmente las tres credenciales temporales; esta guía añade la operación del release EP4.

## Renovar y reconciliar

1. Iniciar el laboratorio y actualizar manualmente las tres credenciales en el archivo AWS del operador. No copiarlas a `.env`, comandos, Git ni capturas.
2. Abrir Ubuntu como `codex` y entrar en este backend.

```bash
source scripts/ep4-env.sh
"$AWS_CLI" sts get-caller-identity --region us-east-1 --output json --no-cli-pager
bash scripts/ep4.sh inspect
```

Comprobar cuenta `002996184293`, rol `voclabs` y región `us-east-1`. El inventario reconoce los siete IDs API originales más los dos IDs registrados en `gateway-journal.json`. Comprueba que las reglas SG/rutas anteriores no cambiaron, tratando las listas AWS como no ordenadas. Si falta algún recurso o la identidad difiere, detenerse y reconciliar: no ejecutar creación automática.

`ep4-toolchain.sh` instala la CLI oficial Linux únicamente en el HOME si falta. `ep4-session-tools.sh` prepara Session Manager y una clave exclusiva para transferencia. No cambian credenciales AWS ni identidad Git. Para otro equipo se puede exportar `AWS_SHARED_CREDENTIALS_FILE` y `AWS_CLI` antes de cargar `ep4-env.sh`.

Si EC2 o RDS propios aparecen detenidos y se desea reanudar su uso en el laboratorio, iniciarlos condicionalmente con los mismos IDs según `ARRANQUE_LABORATORIO.md`. No aumentar capacidad ni crear recursos. Al terminar el arranque, deben estar EC2 `running`, RDS `available`, SSM `Online`, VPC Link `AVAILABLE` y target `healthy`.

## Uso normal

Abrir **https://7k2zyh0t0d.execute-api.us-east-1.amazonaws.com/app/** e iniciar sesión institucional personalmente. No requiere Vite ni Java local funcionando. Catálogo, pedidos y Mi sesión utilizan el Gateway; RabbitMQ actúa después de guardar el pedido y su outbox.

En la EC2 quedan habilitadas las unidades `pedidos360-catalog`, `pedidos360-orders`, `pedidos360-bff`, `pedidos360-receipts`, `pedidos360-insights`, `pedidos360-rabbit-admin` y `pedidos360-rabbit-cluster`. Docker arranca con el host; Compose conserva dos volúmenes propios. Si RDS tarda en estar disponible, revisar las unidades y su recuperación sin reinstalar el release.

Para inspección remota reproducible desde WSL:

```bash
bash scripts/ep4.sh ssm deploy/ep4-inspect-instance.py --output instance-check.json
bash scripts/ep4.sh ssm deploy/ep4-final-verification.py --output final-check.json
python3 scripts/ep4-verify-gateway.py
```

Los scripts SSM se ejecutan únicamente contra la EC2 identificada y etiquetada como Pedidos360. Solo publican salud, hashes, metadatos y salidas seguras. Los archivos `/etc/pedidos360/*.env` y `/etc/pedidos360/ep4/*` permanecen privados en EC2. Los logs HTTP no incluyen Authorization, querystrings ni cuerpos.

## Compilar y probar sin usar AWS

```bash
bash scripts/ep4-build.sh all
bash scripts/ep4-insights-http-test.sh
python3 scripts/ep4-broker.py up
```

El build usa disco Linux bajo `~/.cache/pedidos360-ep4/`. Las pruebas crean sus propios MySQL/brokers Testcontainers. Compose EP4 local usa nodos/volúmenes/red propios, puertos loopback 5674/5675 y 15674/15675, y deja intacto el broker EP3 5672/15672 y los demás proyectos. `status` y `configure` inspeccionan/declararan la topología; no hay comandos prune/reset/down en el wrapper.

## Publicar un release posterior

Compilar/probar primero. `ep4-prepare-release.py` prepara un paquete sin secretos y registra hashes. Para transferir, `ep4.sh transfer setup` añade únicamente una clave propia al usuario ubuntu y fija la clave de host leída por SSM; `transfer tunnel` abre un puerto local 22224 hacia SSH a través de SSM. `transfer upload RUTA_TGZ` copia el paquete. No se añade ingreso SSH al SG.

Después de verificar identidad y el archivo transferido, `ep4-install-release.py` ejecuta el instalador revisado. No repetirlo ciegamente tras una interrupción: comprobar primero el comando SSM registrado, `/var/lib/pedidos360-provision/ep4-install-verification.json`, el symlink `current`, hashes y unidades. Conserva el release previo y copias privadas de entornos/unidades bajo `/var/lib/pedidos360-provision/ep4-backups/`.

El instalador **no cambia las credenciales RDS** ni sustituye la base. Flyway agrega la outbox; no reconstruye tablas anteriores. El fixture JWT de desarrollo no forma parte del paquete.

## Pruebas que alteran solo datos propios de laboratorio

`deploy/ep4-verify.py` añade mensajes diagnósticos inválidos en el broker EP4 y conserva sus DLQ; no purga mensajes. `ep4-order-evidence.py` correlaciona un prefijo de pedido observado en UI con su outbox y tres archivos. El modo `duplicate` republica exactamente ese payload para demostrar idempotencia sin crear otro pedido.

`ep4-recovery.py stop/start` detiene y recupera **solo ambos nodos EP4** y conserva sus volúmenes. Es una prueba de indisponibilidad: utilizarla únicamente cuando se desea repetir ese ensayo. Su baseline impide sobrescribir accidentalmente una prueba anterior; revisar el archivo antes de otro ensayo. No es un procedimiento normal de arranque ni una prueba de HA. El historial de prueba inicial está en `docs/evidence/ep4/cloud-outage.json`, `cloud-outbox-pending.json`, `cloud-recovery.json` y `cloud-recovered-order.json`.

No acceder al SQL, Management o AMQP mediante puertos públicos. El administrador REST y las proyecciones administrativas permanecen en loopback y requieren JWT Admin + Orders.Read. No guardar un token real para probarlos desde CLI. Para iniciar sesión/MFA institucional siempre interviene el usuario.
