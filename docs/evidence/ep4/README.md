# Evidencia técnica EP4

Pruebas ejecutadas el 21 de octubre de 2026. Esta carpeta complementa EP3 y no modifica sus evidencias. El [PDF complementario](../../EP4_IMPLEMENTACION_EVIDENCIAS.pdf) selecciona ocho figuras; la [trazabilidad](../../EP4_TRAZABILIDAD.md) relaciona los once requisitos y ocho indicadores con sus archivos y entorno.

## Capturas y procedencia

`captures.json` registra fuente, fecha y SHA-256. Las vistas `pdf-*` y las capturas de logs presentan datos de ejecuciones reales en una página legible, expresamente identificada; no simulan una consola ni son capturas de la consola AWS. Los archivos JSON originales y los logs se conservan al lado. `ep4-capture.py` permite reproducirlas. Las capturas de la SPA y logout proceden del navegador Codex durante la sesión institucional manual, sin extraer tokens ni almacenamiento de sesión.

| Archivos | Entorno y contenido |
|---|---|
| `01-java-39-tests-wsl.png`, `02-react-tests-build-wsl.png`, `pdf-tests-summary.png` | WSL codex: clean verify, dos tests HTTP posteriores y React/build. Son 41 Java distintas y 11 React; las doce pruebas repetidas no se vuelven a sumar. |
| `03-cluster-two-nodes-wsl.png`, `04-three-queues-three-dlq-wsl.png` | GUI Management real del clúster **local**. No se presenta como tráfico AWS. |
| `05-aws-services.png`, `06-aws-cluster-checks.png`, `pdf-aws-cluster.png` | Resultados SSM del release, salud y clúster **AWS**; no GUI local atribuida a AWS. |
| `07-aws-routing-dlq.png`, `pdf-aws-routing.png` | Enrutamiento direct/topic, controles selectivos/negativos y NACK con x-death=rejected en las tres DLQ de AWS. |
| `08-aws-order-effects.png`, `pdf-aws-acks.png` | Pedido institucional de 30.970 CLP, outbox, tres archivos/ACK y duplicados sin doble efecto en AWS. |
| `09-aws-recovery.png`, `pdf-aws-recovery.png` | Parada/reinicio de los dos nodos propios, outbox pendiente/recuperada y conservación de datos. No prueba de HA. |
| `10-gateway-http.png`, `pdf-gateway-http.png` | HTTP reales y logs seguros del Gateway; SPA cloud y API con 200/201/401/403. |
| `11-cloud-spa-public.png` | SPA cloud antes del login. |
| `12-cloud-order-entra.png`, `13-cloud-recovered-order-entra.png` | Historial real desde la SPA cloud tras ambos pedidos. |
| `14-cloud-catalog-entra.png` | Catálogo real conservado, precios y stock referencial. |
| `15-entra-cloud-logout.png`, `16-cloud-protected-after-logout.png` | Logout Microsoft y retorno al inicio al intentar abrir una ruta protegida. |
| `pdf-entra-cloud.png` | Resumen seguro de la comprobación Entra real; claims visibles de la API, sin el token ni identidad personal. |

## Resultados originales

- Build local: `backend-verify.txt` (39), `insights-http-final.txt` (dos pruebas nuevas además de doce repetidas), `frontend-tests.txt` (11), `frontend-build.txt`. `frontend-build-attempt1.txt` conserva el error inicial corregido; no es el resultado final.
- Inventario: `aws-inventory-before.json` conserva el estado previo; `reconciliation.json` compara identidad, recursos y reglas/rutas; `aws-inventory.json` contiene la lectura final. No se modificaron recursos ajenos/predeterminados.
- Release: `release-manifest.json`, `installation.json` y `aws-final-verification.json`. Los JAR y bytes SPA se contrastan por SHA-256. `deployment-progress.json` es histórico; su campo frontendPresent se obtuvo entonces de una ruta de inspección incorrecta y no invalida el HTTP/hashes posterior.
- RabbitMQ: `cloud-verification.json`, `cloud-order-verification.json`, `cloud-idempotency.json`, `cloud-outage.json`, `cloud-outbox-pending.json`, `cloud-recovery.json` y `cloud-recovered-order.json`.
- Seguridad: `entra-spa-before.json`, `entra-spa-after.json`, `entra-directory.json`, `entra-browser.json`, `gateway-after.json`, `gateway-http.json` y `gateway-access-logs.json`. No contienen Authorization, cookies ni tokens reales.
- `gateway-journal.json` conserva el rechazo de una ruta GET con segmento final vacío, que AWS no creó. Se resolvió con `/app` y `/app/{proxy+}`; no se repite esa escritura rechazada.

## Alcance

Los HTTP 200 Admin y los errores IOException/reintentos acotados se ejecutaron localmente con fixture y broker real. En AWS se comprobó User 403, sin elevar privilegios. No se ejecutó login real Admin ni expiración natural; sí renovación solicitada a Microsoft. El tenant institucional era preexistente. No hay replicación classic ni HA de host. El laboratorio debe estar encendido para acceder al despliegue.
