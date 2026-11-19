# Identificadores nuevos EP5 (cuenta 647660738152)

Fuente: `docs/evidence/ep5/aws/deployment-journal.json` (creados el 2026-11-19). Sustituyen a los IDs de EP4 citados en el informe (EC2 `i-0818fdfafcfb7cb31`, API `7k2zyh0t0d`), que siguen siendo históricos.

| Recurso | Identificador |
|---|---|
| Cuenta AWS / región | 647660738152 / us-east-1 (rol voclabs) |
| VPC | vpc-0b48e978564207a3e (10.36.0.0/16) |
| Subredes | public-b subnet-0d9482ba2929cd737 · private-b subnet-0f87f31d86d3e6993 · private-c subnet-026d7d842cf211bfc |
| Internet Gateway | igw-04b7911085d58b80d |
| Security groups | vpclink sg-09f0f4b26620dee6b · alb sg-09c04431c946ce180 · app sg-04b48443a91df53b3 · db sg-090b97c5589956881 |
| EC2 | i-01bcf3ef9d3a64d4e (t3.large, ami-0719278fd447e399f) |
| RDS | pedidos360-mysql · pedidos360-mysql.c6vvzexjwmq0.us-east-1.rds.amazonaws.com (MySQL 8.4.11, db.t3.micro) |
| ALB interno | pedidos360-internal-alb · internal-pedidos360-internal-alb-1182732690.us-east-1.elb.amazonaws.com |
| Target group | targetgroup/pedidos360-bff-tg/8d47ffba71cd51e8 |
| VPC Link | uk728z |
| HTTP API | az3h2vqgsi · https://az3h2vqgsi.execute-api.us-east-1.amazonaws.com |
| Autorizador JWT / integración | 0ue6up / ea6ze8c |
| URL de la aplicación | https://az3h2vqgsi.execute-api.us-east-1.amazonaws.com/app/ |
| Log group | /pedidos360/api-gateway (7 días) |
| Release instalado | ep5-20261119T163823Z (2026-11-19T16:50Z, pulido visual del frontend; mismos JAR). Antes: ep5-20261119T144015Z (favicon). Las evidencias E-01..E-17 y E-19 se tomaron con ep5-20261119T040026Z (12:45Z); los tres releases difieren solo en el frontend |
| IPv4 pública de la EC2 | dinámica, sin EIP: cambia si el laboratorio detiene la instancia (100.55.75.122 el 2026-11-19 12:30Z); no se usa para entrar |
| App de Entra (SPA) | b4ede06a-cde3-4982-8b79-56fab7264fdd: URI `https://az3h2vqgsi.execute-api.us-east-1.amazonaws.com/app/` añadida el 2026-11-19 (se conservan las 3 anteriores) |
