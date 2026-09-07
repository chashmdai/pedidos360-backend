# Checkpoint AWS — propuesta de FASE 4

**APROBADO por el usuario el 2026-09-06. Ejecutado y verificado en FASE 5/6.** La aprobación explícita comprende la topología, tamaños, costos orientativos y asociación acotada del perfil descritos aquí. Se conserva este plan como referencia de alcance; el registro de acciones y recursos reales está en `docs/evidence/phase5/deployment-journal.json`. Al cerrar FASE 7 el usuario informó que AWS está apagado; no se efectuaron nuevas operaciones AWS después de ese aviso.

## Contexto verificado

Cuenta `002996184293`, rol `voclabs`, sesión `user3301432=BENJAMIN__TORREJON`. No hay región CLI predeterminada. Se propone **us-east-1**, donde existe el stack cloudlab y se verificaron las opciones técnicas. Inventario us-east-1/us-west-2: VPC/subnets/SG/rutas predeterminados y recursos del laboratorio; no se encontraron EC2, RDS, APIs o balanceadores del proyecto en esas consultas. No se declara vacía toda la cuenta.

Evidencias fechadas: [inventario](evidence/phase4/inventory), [identidad](evidence/phase4/identity-and-region.json), [oferta RDS](evidence/phase4/rds-orderable.json), [AMI](evidence/phase4/ubuntu-ami.json), [perfil](evidence/phase4/lab-instance-profile.json). IAM impide leer ciertas políticas, Cloud Map impide ListServices y Pricing impide GetProducts. Esos errores no se trataron como listas vacías ni se intentó elevar permisos. Las lecturas exitosas no prueban permiso de creación.

## Acción propuesta para aprobar

Crear exclusivamente recursos nuevos del proyecto, con Project=Pedidos360, Course=DSY1107 y Environment=lab donde soporten tags:

| Recursos nuevos | Configuración |
|---|---|
| 1 VPC pedidos360-vpc | 10.36.0.0/16, DNS habilitado |
| 3 subnets | Pública 10.36.0.0/24 en us-east-1b; privadas 10.36.10.0/24 en us-east-1b y 10.36.20.0/24 en us-east-1c |
| 1 IGW, 2 route tables y asociaciones | Internet solo en subnet pública; privadas sin default a Internet |
| 4 SG | VPC Link → ALB:80 → EC2:8180; EC2 → RDS:3306; salidas HTTPS; SSH temporal /32 administrativo |
| 1 key pair pedidos360-deploy | Nueva clave exclusiva; importar parte pública; privada fuera de Git; no usar vockey |
| 1 EC2 pedidos360-app + EBS | t3.medium, Ubuntu 24.04 amd64 AMI ami-025d99823a4caad37, 20 GiB gp3 cifrado, IMDSv2, créditos standard |
| 1 RDS pedidos360-mysql | MySQL 8.4.11, db.t3.micro, Single-AZ, 20 GiB gp3 cifrado, privado, backup un día y protección de eliminación |
| Subnet/parameter groups RDS propios | pedidos360-db-subnets; pedidos360-mysql84 con require_secure_transport=ON |
| ALB/TG/listener propios | pedidos360-internal-alb, interno HTTP80; pedidos360-bff-tg a instancia:8180, health /actuator/health |
| VPC Link | pedidos360-vpclink, dos subnets privadas/SG propio |
| HTTP API, authorizer, integración, stage y 7 rutas | pedidos360-http-api, pedidos360-entra-jwt, stage $default; issuer/audience existentes |
| Log group propio | /pedidos360/api-gateway, siete días de retención, sin bearer/queries/cuerpos |

También aprobar **la asociación de LabInstanceProfile preexistente a esa nueva EC2**, únicamente para la administración SSM prevista, sin modificar rol, perfil o políticas. Su pertenencia al laboratorio está verificada. Los service-linked roles de RDS/ELB/API Gateway ya existen y serán usados normalmente por sus servicios, sin editarlos. No se propone crear roles IAM nuevos.

No se modifican las VPC predeterminadas, SG default, vockey, stack cloudlab, funciones/reglas/políticas ajenas ni recursos Entra. No hay NAT Gateway, Cloud Map, S3, CloudFront, ACM, dominio propio, EIP, broker ni Kubernetes en esta propuesta.

## Motivo de la integración privada

El usuario confirmó que no dispone de dominio. La alternativa de un BFF público por HTTP dejaría un tramo de bearer sin TLS. Un proxy HTTPS público necesita resolver certificado/nombre y su mantenimiento. Cloud Map no tiene permisos de lectura suficientes acreditados en este laboratorio. VPC Link + ALB interno ofrece una ruta privada soportada y un health check, sin depender de un dominio propio. [Opciones oficiales](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-private.html).

El tramo público a API Gateway usa HTTPS. VPC Link/ALB/BFF usan HTTP restringido dentro de la VPC; no se presenta como TLS extremo a extremo. RDS usa TLS y verifica identidad mediante su CA/hostname. EC2 pública sirve para salida/administración; su BFF solo acepta al SG del ALB. Catalog/Orders permanecen en loopback. Una sola EC2/RDS Single-AZ no es alta disponibilidad.

## Despliegue y pruebas posteriores

JAR + systemd, tres servicios independientes, Java 25 fijado, build/tests en WSL y artefactos con hash. Credenciales RDS nuevas externas a Git; esquemas y usuarios separados; Flyway por servicio, Hibernate validate y pool acotado. No desplegar el fixture JWT ni ejecutar MySQL local en EC2.

Mantener frontend en localhost:5173. Cambiar solo su API base al endpoint real recibido de AWS; no rediseñar ni crear registros Entra. Gateway valida issuer/audience/firma/vigencia/scopes; BFF y servicios mantienen su propia validación, rol Admin y propiedad tid+oid. Las siete rutas cubren productos/lista/detalle, pedidos/lista/detalle/creación, me y administración.

Después de desplegar se ejecutarán pruebas reales de health, TLS/SQL/Flyway/aislamiento, CORS, 401/403/200/201, MSAL y pedido multítem a través de Gateway hasta RDS. Nada de esto está declarado probado todavía. La sesión de Jazmín sigue no ejecutada; no se autoriza otra asignación temporal de rol como parte del despliegue.

## Costo y límites

Referencia continua: **66.90–72.74 USD por 730 horas**, con 0–1 LCU promedio, antes de llamadas/transferencias/logs/créditos CPU adicionales. Para siete días: base **15.40–16.74 USD**; presupuesto orientativo **18–20 USD** con margen de bajo tráfico. No es un límite automático de facturación ni descuenta Free Tier/créditos de laboratorio. Se desconoce el saldo del laboratorio.

Fuentes y cálculo: [precios RDS verificados](evidence/phase4/rds-public-prices.json), [EC2](https://aws.amazon.com/ec2/instance-types/t3/), [ALB](https://aws.amazon.com/elasticloadbalancing/pricing/), [EBS](https://aws.amazon.com/ebs/general-purpose/), [IPv4](https://aws.amazon.com/vpc/pricing/), [HTTP API](https://aws.amazon.com/api-gateway/pricing/). El informe FASE_4.md de la raíz del workspace conserva el desglose completo y las alternativas.

ALB y almacenamiento cuestan mientras existan. No se ejecutará limpieza por el solo hecho de aprobar creación; retirar RDS implica una decisión explícita sobre snapshot/datos. Si falla un permiso, registrar error y manifiesto parcial, conservar recursos y resolver el bloqueo sin elevar privilegios ni reutilizar infraestructura ajena.

**Confirmación recibida:** «Apruebo el checkpoint y el plan de infraestructura de FASE 4. Continúa con FASE 5 según la propuesta documentada». STS se comprobó nuevamente y coincide con cuenta/rol esperados. Si vence la credencial durante la ejecución, solicitar renovación y conservar los recursos creados.
