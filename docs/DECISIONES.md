# Decisiones de Pedidos360

Estado local cerrado en FASE 3; plan AWS de FASE 4 aprobado y materializado en FASE 5 el 2026-09-06. La pauta académica prevalece y las instrucciones posteriores del usuario sustituyen las propuestas iniciales del prompt maestro. Se priorizó demostrar MSAL, access tokens, JWT, scopes, roles y respuestas HTTP antes de ampliar el negocio.

| Decisión | Motivo y consecuencia |
|---|---|
| React + TypeScript + Vite | Sustitución de Angular autorizada por el docente. MSAL React/Browser cumple login/logout, adquisición y rutas protegidas sin copiar APIs Angular |
| WSL2 canónico | Java/Maven/Node/npm Linux y socket Docker Linux. Windows conserva Codex y navegador. Workspace sigue en `/mnt/c/Users/Benja/Documents/cloudnative/ev1`; no se movió |
| Dos repositorios; backend Maven multimódulo | Estructura aprobada frontend/backend. BFF, Catalog y Orders generan tres JAR independientes, sin dependencias Maven entre contextos |
| DDD/hexagonal proporcionado | Catalog sencillo; Orders con agregado multítem, Money decimal/moneda, OwnerId y snapshots. Domain Java puro separado de JPA y REST DTO |
| Contratos técnicos | `contracts/` contiene OpenAPI y documentación HTTP; no Product/Order compartidos, aggregates, repositorios ni common-domain |
| Mapping explícito | El conjunto pequeño de DTOs no justifica MapStruct/Lombok. Los adaptadores hacen traducciones visibles; dominio sin dependencias de framework |
| RestClient síncrono | Comunicación breve con destinos fijos y timeouts, compatible con Spring MVC. No seguir redirects ni reintentar POST automáticamente |
| MySQL local en Compose | Recurso exclusivo `pedidos360-mysql`, loopback 13306, esquemas y usuarios separados; no servicio MySQL nativo ni túnel remoto como dependencia |
| Flyway por contexto | Migrador propio con DDL y usuario de aplicación con DML; Hibernate validate. No migraciones sobre tablas ajenas |
| MySQL real en Testcontainers | Prueba tipos, transacciones, SQL, precisión y migraciones de la misma familia que desarrollo. Sin H2. Recursos de test identificados y limpieza limitada a ellos |
| Un recurso OAuth inicial | SPA, BFF y servicios comparten audience de la API propia. Cada Resource Server verifica firma, issuer, audience, vigencia, tid, azp, versión y oid; bearer propagado explícitamente |
| Tres scopes exactos | Catalog.Read, Orders.Read, Orders.Create. Crear exige también Catalog.Read para snapshots. Orders.Write no se registró ni se usa como autorización |
| Admin AND Orders.Read | Rol no sustituye scope. Consulta administrativa separada y limitada al tenant; Mis pedidos conserva filtro tid+oid incluso para Admin |
| MSAL + PKCE, sin secreto SPA | Access token adquirido silenciosamente, fallback interactivo cuando corresponde, caché sessionStorage gestionada por MSAL; no ID token como bearer |
| Claims de diagnóstico limitados | `/me` devuelve solo campos permitidos, con no-store y sin JWT. El frontend muestra claims validados por el BFF; no autoriza negocio por una decodificación local |
| Prueba Admin temporal | Variante explícitamente aprobada ante indisponibilidad de Jazmín: 200 real, retirada de esa única asignación y token nuevo User con 403. No prueba un login de Jazmín |
| Diseño visual conservado | Se mantuvo la base manual del usuario. Las vistas de sesión y administración reutilizan su presentación. Sin cambios CSS en FASE 2/3 |

## Decisiones AWS aprobadas en FASE 4 y ejecutadas en FASE 5

El inventario previo confirmó cuenta/rol esperados, recursos predeterminados y del laboratorio, y ausencia de EC2/RDS/APIs/balanceadores de Pedidos360 en las dos regiones consultadas. Se eligió us-east-1 de forma explícita; no se cambió la región CLI global. El usuario confirmó que no dispone de dominio propio.

El [checkpoint AWS](AWS_CHECKPOINT.md) aprobó VPC propia, una EC2 t3.medium con JAR+systemd, RDS privado MySQL 8.4.11/db.t3.micro/gp3 y HTTP API con VPC Link+ALB interno. Se crearon y verificaron esos recursos en FASE 5. ALB se justifica por el destino privado y la ausencia de dominio para un proxy público HTTPS; Cloud Map tuvo permisos de listado denegados. No se añadió NAT Gateway ni hosting frontend. LabInstanceProfile se asoció a la EC2 propia sin modificarlo ni cambiar sus políticas.

La versión exacta 8.4.11 y la clase RDS se comprobaron primero en la oferta y luego en la instancia creada. TLS, conectividad, migraciones y aislamiento se verificaron realmente. Presupuesto de bajo tráfico de referencia: 18–20 USD por una semana continua, con supuestos en el checkpoint; no es un límite automático de facturación.

### Alternativas y alcance

Docker para infraestructura local y Testcontainers son decisiones cerradas. EC2 usa JAR + systemd por los artefactos ya probados y por evitar distribuir imágenes en este bloque. Compose sigue siendo una alternativa válida para una evolución posterior; esta elección no afecta Docker local.

HTTP API con JWT authorizer y rutas explícitas cubre el alcance de la evaluación. La topología privada y el costo de ALB/VPC Link fueron aprobados; no se incorporaron NAT Gateway ni Cloud Map. El BFF refuerza la conjunción de scopes, roles y propiedad que no resuelve el authorizer por sí solo.

RDS, desarrollo y Testcontainers usan MySQL 8.4.11. Se desplegó db.t3.micro Single-AZ, almacenamiento gp3 de 20 GiB y conexiones TLS con verificación de CA/hostname. Las evidencias distinguen el inventario previo de las pruebas ejecutadas después de la creación.

El frontend puede demostrarse en localhost:5173. S3, CloudFront, ACM y hosting público no son requisitos actuales. Eventos, broker, outbox, CQRS, Kubernetes, pagos e inventario quedan fuera del alcance implementado.

Los checkpoints de credenciales y creación fueron satisfechos por el usuario; STS coincidió con cuenta/rol esperados. La reanudación del laboratorio reconcilió los mismos IDs antes de continuar. Ante futuras credenciales vencidas, detenerse y solicitar renovación; no modificar perfiles ni políticas para continuar.

La instalación usa carpetas de release explícitamente 0755 y environments 0600: la máscara privada de secretos no debe impedir que systemd acceda a los JAR. SSM permite verificar/reanudar una release sin reaprovisionar datos; el ingreso SSH temporal se retira después de transferir y verificar el canal SSM. API Gateway controla CORS en cloud; el BFF mantiene su validación JWT/roles/scopes y se deshabilita únicamente su filtro CORS en el perfil cloud.
