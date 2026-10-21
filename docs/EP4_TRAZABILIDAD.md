# Trazabilidad técnica EP4

Fecha: 21 de octubre de 2026. Contrasto los once requisitos específicos y los ocho indicadores de la pauta oficial. **Verificado** describe la evidencia y su entorno; no atribuye una calificación. Las capturas son pantallas reales o vistas expresamente identificadas de resultados reales. La EP3 permanece intacta.

## Requisitos específicos

| ID | Estado / alcance comprobado | Evidencia actual |
|---|---|---|
| P01 | Verificado AWS: HTTP API existente 7k2zyh0t0d activo; no se recreó | [Inventario](evidence/ep4/aws-inventory.json), [Gateway](evidence/ep4/gateway-after.json) |
| P02 | Verificado AWS: VPC Link, integración HTTP_PROXY hacia listener ALB, target saludable y stage automático | [Reconciliación](evidence/ep4/reconciliation.json), [integraciones y rutas](evidence/ep4/gateway-after.json) |
| P03 | Verificado: SPA cloud consume el Gateway; catálogo, sesión, POST y GET de pedidos | [CloudWatch HTTP](evidence/ep4/gateway-access-logs.json), [pedido](evidence/ep4/12-cloud-order-entra.png), [catálogo](evidence/ep4/14-cloud-catalog-entra.png) |
| P04 | Verificado AWS: authorizer JWT, 401 ausente/inválido y 200/201 con Entra real; User 403 lo impone BFF | [HTTP público](evidence/ep4/gateway-http.json), [JWT config](evidence/ep4/gateway-after.json), [sesión real](evidence/ep4/entra-browser.json), [logs](evidence/ep4/gateway-access-logs.json) |
| P05 | Verificada existencia actual del tenant institucional, usuarios, aplicaciones y asignaciones. Su creación histórica no se repite ni se atribuye a EP4 | [Graph directorio](evidence/ep4/entra-directory.json), [SPA después](evidence/ep4/entra-spa-after.json) |
| P06 | Verificado: OAuth2/OIDC code + PKCE con MSAL, intervención institucional manual, audience/scopes/rol y renovación aceptados | [Entra real](evidence/ep4/entra-browser.json), [auth.ts](https://github.com/chashmdai/pedidos360-frontend/blob/main/src/auth.ts), [registro de Gateway](evidence/ep4/gateway-access-logs.json) |
| P07 | Verificado AWS: frontend en EC2 por HTTPS Gateway y seis servicios saludables; bytes SPA y JAR contrastados con release | [HTTP y hashes SPA](evidence/ep4/gateway-http.json), [verificación final AWS](evidence/ep4/aws-final-verification.json), [manifest](evidence/ep4/release-manifest.json) |
| P08 | Verificado AWS: los dos nodos muestran los mismos dos miembros, sin particiones; también se probó con dos nodos Testcontainers | [Cluster AWS](evidence/ep4/cloud-verification.json), [Java](evidence/ep4/backend-verify.txt), [recuperación](evidence/ep4/cloud-recovery.json) |
| P09 | Verificado AWS: tres colas con un consumidor cada una, tres DLQ separadas, rechazo x-death=rejected por cada flujo y tres efectos/ACK | [Colas/rutas/DLQ](evidence/ep4/cloud-verification.json), [efectos](evidence/ep4/cloud-order-verification.json), [estado final](evidence/ep4/aws-final-verification.json) |
| P10 | Verificado AWS: direct original, binding exchange-to-exchange hacia topic, patrones selectivos positivos y controles negativos reales | [routingTests y bindings](evidence/ep4/cloud-verification.json), [configuración](../messaging-support/src/main/resources/pedidos-rabbit.properties) |
| P11 | Verificado AWS: Docker Compose 2.40.3 levantó dos nodos 4.2.9 en EC2 y recuperó los mismos contenedores/volúmenes | [Instalación](evidence/ep4/installation.json), [versiones](evidence/ep4/host-preparation.json), [recuperación](evidence/ep4/cloud-recovery.json) |

La propiedad/administración del tenant institucional no corresponde a este proyecto. P05 acredita su existencia y uso autorizado, no una nueva alta del tenant. No hay sesión real de la cuenta Admin en esta iteración: Graph acredita la asignación existente; los HTTP 200 administrativos se prueban con fixture local firmado, y Entra User real acredita 403 sin elevación.

## Indicadores ponderados

| ID | Peso | Archivos principales | Pruebas / evidencia | Estado |
|---|---:|---|---|---|
| R1 | 12% | `messaging-support/.../pedidos-rabbit.properties`, `MessagingProperties`, `InsightsTopology.Names`; bootstrap lee el mismo archivo | ClusterRoutingIntegrationTest y [bindings cloud](evidence/ep4/cloud-verification.json) | Verificado: nombres productivos centralizados |
| R2 | 13% | `MessagingConfiguration`, `InsightsTopology` | Beans productivos declarados en Testcontainers y topología efectiva de AWS | Verificado: cada flujo y DLQ con Queue/Exchange/Binding |
| R3 | 10% | Configuraciones AMQP, `ProjectionStore`, dominio `SalesSummary`, aplicación Orders intacta | Pruebas de dominio, rollback outbox y revisión de dependencias | Verificado: dominio/controladores no declaran AMQP |
| R4 | 15% | `ReceiptListener`, `audit/AuditListener`, `sales/SalesListener` | Tres consumidores activos AWS y [tres ACK](evidence/ep4/cloud-order-verification.json) | Verificado: listeners separados por responsabilidad |
| R5 | 20% | `ReceiptListener`, `ManualProjectionConsumer`, `FileProjectionStore`, publisher outbox | 15 pruebas unitarias de consumidores; NACK/DLQ cloud, [duplicados](evidence/ep4/cloud-idempotency.json), [outbox pendiente](evidence/ep4/cloud-outbox-pending.json), [recuperación](evidence/ep4/cloud-recovered-order.json) | Verificado; fallos de almacenamiento/reintentos limitados en WSL, broker y DLQ también en AWS |
| R6 | 13% | `RabbitAdminController`, contrato REST EP3 + [extensión EP4](../contracts/ep4-admin-and-insights.openapi.yaml) | AdminRestIntegrationTest: HTTP con broker real; JWT, namespaces y códigos | Verificado en WSL; servicio desplegado privado/401 en AWS |
| R7 | 10% | `RabbitAdminService`: CRUD y `updateQueuePolicy`; cambios de enrutamiento vía bindings | Actualización TTL/límite 200; incompatibilidad 409 sin recrear; namespace de negocio 403 | Verificado: actualización segura viable; tipo/durabilidad de exchange siguen inmutables |
| R8 | 7% | DTO `AdminRequests`, validación de nombres en servicio y límites de política | AdminValidationTest, AdminRestIntegrationTest; vacíos/rangos/argumentos/roles | Verificado con HTTP y broker real en WSL |

Total de pesos: 100%. No equivale a una nota otorgada. Los dos nodos en una EC2 y las colas classic **no acreditan HA**.

## Regresión y correspondencia de versión

La pasada completa ejecutó 39 pruebas Java y el test HTTP adicional de Insights añadió 2 nuevas: **41 distintas**, sin fallos ni omitidas. El módulo Insights repitió sus otras 12 pruebas durante esa pasada adicional; no las sumo dos veces. React ejecutó 11 pruebas y build de producción. Fuentes: [clean verify](evidence/ep4/backend-verify.txt), [HTTP Insights](evidence/ep4/insights-http-final.txt), [React](evidence/ep4/frontend-tests.txt), [build](evidence/ep4/frontend-build.txt).

Los hashes de las filas iniciales de RDS no cambiaron. Quedaron 2 productos, 4 pedidos y 7 líneas: únicamente se añadieron los dos pedidos de verificación EP4. Se conservó el contenido anterior de las DLQ y los archivos persistentes después del reinicio. El [manifiesto](evidence/ep4/release-manifest.json) y el [estado final](evidence/ep4/aws-final-verification.json) permiten contrastar los JAR; `gateway-http.json` contrasta HTML/JS/CSS servidos con los bytes del release.

## Límites de lo probado

No ejecuté pérdida permanente de nodos/host ni afirmo replicación classic. No ejecuté login real de la cuenta Admin ni expiración natural de sesión; probé renovación solicitada a Microsoft. La administración 200 y los fallos IOException de consumidores se prueban localmente con fixture y recursos aislados; no se presentan como pruebas Entra o de esos fallos específicos en AWS. Las dos alertas altas de dependencias frontend documentadas en EP3 permanecen fuera de esta evolución; no añadí dependencias npm.
