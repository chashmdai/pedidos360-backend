# Capturas EP3 completadas

Conservo el nombre histórico de este archivo para no romper referencias. Las capturas locales y Entra ya están completadas. React está autorizado por el docente.

Usé Chromium/Playwright en WSL como `codex` y el navegador integrado de Codex para la sesión institucional. No capturé contraseñas, MFA, tokens ni almacenamiento de sesión.

Las imágenes de logs/JSON son vistas explícitas de evidencia ejecutada. No simulan una terminal ni otra interfaz. Los originales de broker/SPA se conservan; el PDF recorta detalles sin alterar esos archivos.

El formulario institucional está en 19; el resultado 201 y comprobante/ACK están en `entra-verification.json`, access logs y `pdf-flow.png`. La captura 20 muestra pedidos previos, no la tarjeta del nuevo pedido. La renovación 18 muestra su resultado verificado sin la identidad privada del usuario.

| Captura real | Fuente / descripción |
|---|---|
| [01-java-tests.png](01-java-tests.png) | Vista explícita de archivos/resultados ejecutados; no consola simulada |
| [02-react-tests-build.png](02-react-tests-build.png) | Vista explícita de archivos/resultados ejecutados; no consola simulada |
| [03-rabbit-overview.png](03-rabbit-overview.png) | Broker propio operativo, un nodo |
| [04-rabbit-exchanges.png](04-rabbit-exchanges.png) | Pantalla real de RabbitMQ Management |
| [05-rabbit-queues.png](05-rabbit-queues.png) | Pantalla real de RabbitMQ Management |
| [05b-rabbit-bindings.png](05b-rabbit-bindings.png) | Bindings reales expandidos; exchange y routing key de negocio |
| [05c-rabbit-binding-table.png](05c-rabbit-binding-table.png) | Detalle real de la tabla de bindings; recorte nativo para legibilidad en PDF |
| [06-frontend-order-local.png](06-frontend-order-local.png) | Pedido creado en la SPA real con respuesta 201; modo local |
| [07-ack-retry-nack.png](07-ack-retry-nack.png) | Vista explícita de archivos/resultados ejecutados; no consola simulada |
| [08-rabbit-dlq.png](08-rabbit-dlq.png) | Pantalla real de RabbitMQ Management |
| [08b-dlq-message-xdeath.png](08b-dlq-message-xdeath.png) | Vista de respuesta HTTP real de RabbitMQ; x-death rejected; no pantalla GUI simulada |
| [09-admin-http.png](09-admin-http.png) | Vista explícita de archivos/resultados ejecutados; no consola simulada |
| [10-broker-recovery.png](10-broker-recovery.png) | Vista explícita de archivos/resultados ejecutados; no consola simulada |
| [11-order-receipt.png](11-order-receipt.png) | Vista explícita de archivos/resultados ejecutados; no consola simulada |
| [12-frontend-catalog-local.png](12-frontend-catalog-local.png) | Frontend original, sesión fixture local explícita |
| [13-message-ready.png](13-message-ready.png) | Pedido real persistido/publicado, consumidor propio temporalmente detenido: Ready |
| [14-message-unacked.png](14-message-unacked.png) | Entrega real Unacked durante reintento controlado; demora temporal de cinco segundos |
| [15-message-acked.png](15-message-acked.png) | Almacenamiento recuperado, ACK explícito y cola sin entregas pendientes |
| [16-entra-catalog.png](16-entra-catalog.png) | Pantalla real mediante navegador integrado; sin credenciales ni tokens |
| [17-entra-admin-403.png](17-entra-admin-403.png) | Pantalla real mediante navegador integrado; sin credenciales ni tokens |
| [18-entra-msal-renewal.png](18-entra-msal-renewal.png) | Vista legible de evidencia ejecutada para PDF; no terminal simulada |
| [19-entra-order-form.png](19-entra-order-form.png) | Pantalla real mediante navegador integrado; sin credenciales ni tokens |
| [20-entra-history-preserved.png](20-entra-history-preserved.png) | Vista real de pedidos anteriores conservados en la sesión Entra; no muestra la tarjeta del nuevo pedido |
| [21-entra-logout.png](21-entra-logout.png) | Pantalla real mediante navegador integrado; sin credenciales ni tokens |
| [22-entra-route-protected.png](22-entra-route-protected.png) | Pantalla real mediante navegador integrado; sin credenciales ni tokens |
| [pdf-admin.png](pdf-admin.png) | Vista legible de evidencia ejecutada para PDF; no terminal simulada |
| [pdf-dlq.png](pdf-dlq.png) | Vista legible de evidencia ejecutada para PDF; no terminal simulada |
| [pdf-errors.png](pdf-errors.png) | Vista legible de evidencia ejecutada para PDF; no terminal simulada |
| [pdf-flow.png](pdf-flow.png) | Vista legible de evidencia ejecutada para PDF; no terminal simulada |
| [pdf-java.png](pdf-java.png) | Vista legible de evidencia ejecutada para PDF; no terminal simulada |
| [pdf-react.png](pdf-react.png) | Vista legible de evidencia ejecutada para PDF; no terminal simulada |
| [pdf-recovery.png](pdf-recovery.png) | Vista legible de evidencia ejecutada para PDF; no terminal simulada |
| [pdf-security.png](pdf-security.png) | Vista legible de evidencia ejecutada para PDF; no terminal simulada |
| [pdf-topology.png](pdf-topology.png) | Vista legible de evidencia ejecutada para PDF; no terminal simulada |

El manifiesto `captures.json` conserva URL/fuente, fecha y SHA-256. El PDF principal está en `../../EP3_RABBITMQ_EVIDENCIAS.pdf`.

## Repetición controlada

Desde WSL `codex`, con el runtime local y broker propios iniciados:

```bash
python3 scripts/verify-ep3.py --restart-broker
~/.local/share/pedidos360-ep3/evidence-venv/bin/python scripts/ep3-capture.py
~/.local/share/pedidos360-ep3/evidence-venv/bin/python scripts/ep3-observe-delivery.py
~/.local/share/pedidos360-ep3/evidence-venv/bin/python scripts/ep3-capture-details.py
```

Los scripts locales agregan pedidos de prueba y detienen únicamente procesos/broker EP3 identificados. No ejecutarlos contra el perfil Entra. Su login/MFA siempre es manual. No repetir Entra mediante fixtures ni publicar archivos de sesión.

Para regenerar el PDF a partir de evidencia ya verificada: `python scripts/ep3-create-pdf.py` y `python scripts/ep3-pdf-qa.py`, usando el venv con `scripts/requirements-evidence.txt`. Revisar todas las páginas renderizadas antes de entregar.
