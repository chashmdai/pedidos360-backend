# Arrancar Pedidos360 después de renovar el laboratorio AWS

Esta guía reanuda la infraestructura ya creada. **No ejecuta las etapas `network`, `database`, `compute` ni `gateway` de `aws_deploy.py`**, porque esas etapas crean recursos y ya fueron completadas. Los identificadores reales están registrados en el journal de FASE 5.

Última comprobación operativa: **2026-09-12**. La cuenta/rol coincidieron, todos los IDs se reconciliaron, EC2 estaba `running`, RDS `available`, SSM `Online`, el target `healthy`, VPC Link `AVAILABLE`, el frontend respondió HTTP 200 y una ruta protegida sin token respondió HTTP 401.

Arquitectura utilizada al ejecutar la demostración:

```text
React/Vite en WSL (localhost:5173)
  → Microsoft Entra
  → API Gateway HTTPS
  → VPC Link
  → ALB interno
  → BFF, Catalog y Orders en EC2
  → RDS MySQL privado
```

## 1. Iniciar el laboratorio y actualizar las credenciales

1. Inicia el laboratorio AWS y espera hasta que la consola indique que está listo.
2. En los detalles de AWS del laboratorio, abre las credenciales para AWS CLI.
3. Sustituye el bloque `[default]` en:

   ```text
   C:\Users\Benja\.aws\credentials
   ```

   Debe contener las **tres** propiedades temporales entregadas por el laboratorio:

   ```ini
   [default]
   aws_access_key_id=<valor nuevo>
   aws_secret_access_key=<valor nuevo>
   aws_session_token=<valor nuevo>
   ```

No pegues esos valores en el repositorio, archivos `.env`, comandos guardados, capturas ni este documento. No es necesario ejecutar `aws configure` ni definir una región global; Pedidos360 usa `us-east-1` explícitamente.

Abre PowerShell y comprueba la identidad:

```powershell
aws sts get-caller-identity --region us-east-1 --output json --no-cli-pager
```

El resultado correcto debe mostrar:

```text
Account: 002996184293
Arn: arn:aws:sts::002996184293:assumed-role/voclabs/...
```

Si aparece `ExpiredToken`, `InvalidClientTokenId` o una cuenta/rol diferente, detente y vuelve a copiar las tres credenciales. No continúes con otra cuenta.

## 2. Reconciliar los recursos existentes

Desde PowerShell, entra a WSL:

```powershell
wsl -d Ubuntu
```

En WSL ejecuta:

```bash
cd /mnt/c/Users/Benja/Documents/cloudnative/ev1/pedidos360-backend
export AWS_CLI=/mnt/c/Users/Benja/AppData/Local/Programs/Amazon/AWSCLIV2/aws.exe
"$AWS_CLI" sts get-caller-identity --region us-east-1 --output json --no-cli-pager
python3 scripts/reconcile-aws.py
```

La última línea esperada es:

```text
All recorded IDs reconciled; default SG and route rules unchanged; seven route IDs match.
```

La reconciliación es de solo lectura. Si informa un recurso ausente o un ID distinto, no ejecutes scripts de creación: revisa el journal y el estado del laboratorio.

## 3. Arrancar EC2 y RDS solo si están detenidos

Consulta sus estados desde WSL:

```bash
"$AWS_CLI" ec2 describe-instances \
  --region us-east-1 \
  --instance-ids i-0818fdfafcfb7cb31 \
  --query 'Reservations[0].Instances[0].State.Name' \
  --output text --no-cli-pager

"$AWS_CLI" rds describe-db-instances \
  --region us-east-1 \
  --db-instance-identifier pedidos360-mysql \
  --query 'DBInstances[0].DBInstanceStatus' \
  --output text --no-cli-pager
```

Para EC2:

- Si responde `running`, no hagas nada.
- Si responde `stopped`, ejecuta:

  ```bash
  "$AWS_CLI" ec2 start-instances \
    --region us-east-1 \
    --instance-ids i-0818fdfafcfb7cb31 \
    --no-cli-pager

  "$AWS_CLI" ec2 wait instance-running \
    --region us-east-1 \
    --instance-ids i-0818fdfafcfb7cb31
  ```

Para RDS:

- Si responde `available`, no hagas nada.
- Si responde `stopped`, ejecuta:

  ```bash
  "$AWS_CLI" rds start-db-instance \
    --region us-east-1 \
    --db-instance-identifier pedidos360-mysql \
    --no-cli-pager

  "$AWS_CLI" rds wait db-instance-available \
    --region us-east-1 \
    --db-instance-identifier pedidos360-mysql
  ```

Si el estado es `pending`, `starting`, `stopping` o similar, espera y vuelve a consultar. No envíes otra orden de inicio mientras exista una transición.

## 4. Esperar a que el backend quede saludable

Ejecuta:

```bash
python3 scripts/aws_deploy.py status
```

El estado listo debe incluir:

```text
EC2 i-0818fdfafcfb7cb31: running
SSM: ... "status": "Online"
RDS: available
Target health: ... "State": "healthy"
VPC Link: AVAILABLE
```

Después de arrancar EC2 o RDS puede tardar varios minutos en aparecer `healthy`. Las unidades systemd están habilitadas y arrancan con EC2; no hay que volver a instalar los JAR.

Si EC2 está `running` pero el target sigue `unhealthy`, revisa las unidades propias mediante SSM Run Command:

```bash
"$AWS_CLI" ssm send-command \
  --region us-east-1 \
  --instance-ids i-0818fdfafcfb7cb31 \
  --document-name AWS-RunShellScript \
  --comment 'Pedidos360 status only' \
  --parameters 'commands=["systemctl --no-pager --full status pedidos360-bff pedidos360-catalog pedidos360-orders"]' \
  --no-cli-pager
```

El comando devuelve un `CommandId`. Consulta su resultado reemplazando el marcador:

```bash
"$AWS_CLI" ssm get-command-invocation \
  --region us-east-1 \
  --command-id <CommandId> \
  --instance-id i-0818fdfafcfb7cb31 \
  --no-cli-pager
```

No abras SSH ni puertos públicos para diagnosticar. El ingreso SSH temporal fue retirado; SSM es el canal administrativo previsto.

## 5. Iniciar el frontend en WSL

Comprueba primero si existe un proceso Pedidos360 registrado:

```bash
bash scripts/dev.sh status
```

Si muestra un frontend `RUNNING`, ya está iniciado. Si hay procesos locales Java o un frontend anterior ejecutándose y quieres cambiar al modo AWS, detén únicamente los procesos propios registrados:

```bash
bash scripts/dev.sh stop
```

Inicia la SPA apuntando a API Gateway:

```bash
bash scripts/dev.sh start cloud
bash scripts/dev.sh status
```

Resultado esperado:

```text
READY Pedidos360 frontend: http://127.0.0.1:5173
Authentication mode: cloud
frontend: RUNNING (port 5173)
```

Mantén abierta la terminal WSL. El modo `cloud` inicia solo React/Vite; BFF, Catalog, Orders y MySQL se ejecutan en AWS.

## 6. Verificar que todo funciona

Sin iniciar sesión, API Gateway debe rechazar una ruta protegida con HTTP 401:

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" `
  https://7k2zyh0t0d.execute-api.us-east-1.amazonaws.com/api/v1/productos
```

Abre en el navegador:

```text
http://localhost:5173
```

Recorrido recomendado:

1. Iniciar sesión con Microsoft Entra.
2. Abrir **Mi sesión** y comprobar el rol `User` y los scopes `Catalog.Read`, `Orders.Read`, `Orders.Create`.
3. Abrir **Catálogo** y comprobar que aparecen Café de especialidad y Taza de cerámica.
4. Abrir **Mis pedidos** para comprobar la lectura desde RDS.
5. Usar **Comprobar acceso Admin**: una cuenta User debe recibir HTTP 403.
6. Usar **Renovar sesión**: la aplicación debe indicar que Microsoft emitió/admitió el token renovado.

Las pruebas de creación agregan datos reales al RDS del laboratorio. Hazlas solo cuando necesites demostrar el POST 201. Un ejemplo ya acreditado fue un pedido con dos cafés y una taza, total 30.970 CLP.

## 7. Detener la ejecución

Para detener solo el frontend local:

```bash
cd /mnt/c/Users/Benja/Documents/cloudnative/ev1/pedidos360-backend
bash scripts/dev.sh stop
```

Después puedes detener o finalizar el laboratorio desde su interfaz. No uses `aws_deploy.py` para apagar y no elimines VPC, RDS, ALB, API Gateway ni otros recursos. Al iniciar otra sesión, repite esta guía desde la renovación de las tres credenciales.

## Datos de referencia

| Elemento | Valor |
|---|---|
| Cuenta AWS | `002996184293` |
| Rol | `voclabs` |
| Región | `us-east-1` |
| EC2 | `i-0818fdfafcfb7cb31` |
| RDS | `pedidos360-mysql` |
| API Gateway | `https://7k2zyh0t0d.execute-api.us-east-1.amazonaws.com` |
| Frontend | `http://localhost:5173` |

La IP pública de EC2 puede cambiar al reiniciar. No se utiliza en el frontend: la SPA siempre apunta al endpoint estable de API Gateway.
