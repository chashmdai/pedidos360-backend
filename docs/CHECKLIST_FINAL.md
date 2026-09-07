# Checklist de entrega — DSY1107

La sustitución de Angular por React está autorizada por el docente según instrucción del usuario. Esta matriz acredita hechos observados; la calificación corresponde al docente.

| Indicador / requisito | Implementación y evidencia |
|---|---|
| MSAL y SPA (60%) | React + MSAL React/Browser, Authorization Code + PKCE; configuración pública exacta de tenant/SPA/API/scopes |
| Login/logout | [Navegador cloud](evidence/phase6/browser-e2e.md): login real, logout Microsoft con retorno automático |
| Guards / interceptor equivalente | Rutas protegidas React: cinco redirecciones anónimas probadas. Cliente API central adquiere access token, adjunta bearer y maneja 401/403 |
| Adquisición / renovación | `acquireTokenSilent`, fallback exclusivo InteractionRequired probado por Vitest; forceRefresh real desde Microsoft aceptado por Gateway/BFF. No se esperó expiración natural |
| Roles y scopes | `/me` expone allowlist de claims validados; User y tres scopes comprobados. Admin 403 real en AWS; Admin 200 controlado y real temporal en FASE 2, ya retirado |
| Consumo API Gateway | [CloudWatch](evidence/phase6/gateway-access-events.json): 200, 201 y 403; siete rutas con JWT Authorizer, scopes y CORS exactos |
| BFF JWT (40%) | Nimbus/Spring Security valida firma, issuer, audience, expiración/nbf, tid, azp, versión y owner; scopes/roles en reglas reales |
| Rechazos independientes | [Cloud](evidence/phase6/cloud-processes-security.json): diez 401 en BFF/Catalog/Orders. [Gateway](evidence/phase5/cloud-http-negative.json): 19 checks de rechazo/CORS |
| Casos adversos | Tests Java con firmas RSA y MySQL real: firma, issuer, audience, expiración, nbf, scopes/roles, claims ausentes, aislamiento de propietario/tenant. No se presentan fixtures como Entra real |
| Compilación backend | [mvn clean verify](evidence/phase5/maven-verify.txt): 13 tests, cero fallos/errores/omitidos; tres JAR independientes |
| Frontend completo | 10 tests y build TypeScript/Vite aprobados; evidencia en repositorio frontend. CSS manual conservado por SHA-256 |
| Persistencia cloud | [TLS y Flyway](evidence/phase5/runtime-verification.json): MySQL 8.4.11, CA/hostname verificados, dos esquemas, usuarios y migradores aislados; denegaciones 1142 |
| End-to-end | [Pedido real en RDS](evidence/phase6/rds-order-and-service-access.json): dos líneas por 30.970 CLP, snapshots, OwnerId y recuperación por SPA |
| EC2 / red / tamaños | [Auditoría](evidence/phase5/infrastructure-audit.json): 20 checks; t3.medium, db.t3.micro, EBS/RDS 20 GiB cifrados, sin Multi-AZ ni recursos extra |
| Recursos ajenos | Reconciliación de IDs y comparación del SG/rutas default con inventario; Docker conserva seis contenedores ajenos y sus estados, sin operaciones sobre ellos |
| Código y contratos | DDD/hexagonal proporcionado, dominio/JPA/REST separados, Order multítem, BigDecimal+moneda, RestClient, OpenAPI técnico sin common-domain |
| Secretos / Git | `.gitignore` excluye secretos, claves, targets y dependencias. Revisión de archivos versionables sin coincidencias de contraseñas conocidas, claves privadas, JWT completos o AWS access keys; ver [revisión](evidence/phase7/source-safety-check.json) |

Los JAR desplegados corresponden al build Java comprobado y sus hashes se verificaron nuevamente en EC2. No se volvió a compilar código sin cambios para presentar una fecha más reciente. La corrección de permisos afectó al instalador/directorio de release, sin cambiar esos JAR. Las validaciones posteriores de Python/Bash/JSON y whitespace corresponden a los scripts/documentos finales.

## Límite aceptado y operación

La sesión real de Jazmín no está ejecutada; falta su disponibilidad/credenciales/MFA. No bloqueó el cierre acordado de FASE 2: Graph acredita su rol Admin y la prueba temporal funcional acredita esa autorización. No se inventa un Admin 200 cloud.

El frontend se demuestra en localhost:5173; no hay S3/CloudFront/dominio. EC2/RDS son de laboratorio, sin alta disponibilidad. El costo orientativo aprobado sigue vigente y no es un límite de facturación. No se limpia infraestructura/datos automáticamente. Antes de reanudar un laboratorio, renovar credenciales, ejecutar STS y reconciliar el journal. La IP pública EC2 puede cambiar; Gateway conserva el endpoint usado por la SPA.

Entregar los dos repositorios GitHub al docente mediante el mecanismo académico indicado. No se ha enviado correo ni entregado AVA automáticamente.
