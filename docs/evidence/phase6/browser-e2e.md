# Navegador real — FASE 6, 2026-09-06

SPA `http://localhost:5173` en modo cloud, API base `https://7k2zyh0t0d.execute-api.us-east-1.amazonaws.com/api/v1`. Se conservó el CSS del diseño manual. Se usó el navegador de Codex, misma pestaña para login, pedido, renovación, logout y protección de rutas. No se inspeccionó/copió el almacenamiento de tokens.

## Observado

1. Iniciar sesión navegó a Microsoft y volvió a Pedidos360 autenticado. En esta ejecución no fue necesario solicitar contraseña/MFA al usuario; no se declara una aprobación MFA nueva.
2. Mi sesión mostró `be.torrejons@duocuc.cl`, rol **User**, scopes **Catalog.Read, Orders.Read, Orders.Create**, tenant/issuer propios, audience `114f7b58-b207-4d46-9d6e-f491c3a0c0e0`, azp de la SPA y versión 2.0. Son datos devueltos por el BFF que valida el bearer, no claims confiados al navegador.
3. Comprobar Admin mostró **HTTP 403**. CloudWatch y el access log BFF registran ese resultado.
4. Catálogo mostró Café de especialidad ($8.990) y Taza de cerámica ($12.990). Formulario: café cantidad 2, taza cantidad 1; estimado $30.970. Se pulsó Registrar una sola vez; el botón quedó deshabilitado durante el envío.
5. Mis pedidos mostró **9F82F14F**, estado Registrado, dos líneas y total **$30.970**, fecha visible 06-09-2026 16:49:22 UTC−03. Recargar la pestaña recuperó el mismo pedido.
6. Renovar sesión mostró «Renovación solicitada a Microsoft; la API aceptó el token». La adquisición pasó de caché MSAL a Microsoft; emisión visible cambió de 16:38:37 a 16:47:56 y vencimiento de 17:58:42 a 18:12:37. Se acredita `forceRefresh` y aceptación de token nuevo; no expiración natural ni una nueva interacción MFA.
7. Comprobar Admin nuevamente devolvió **HTTP 403** con la sesión renovada. El rol siguió siendo User.
8. Cerrar sesión navegó al endpoint Microsoft; mostró cierre de cuenta y volvió automáticamente al inicio de la SPA, con Iniciar sesión y sin Mi sesión.
9. Navegación directa, en la misma pestaña ya anónima, a `/catalogo`, `/pedidos`, `/nuevo`, `/sesion`, `/administracion`: **las cinco redirigieron a `/`** y mostraron Iniciar sesión.

## Contraste independiente

[CloudWatch](gateway-access-events.json) registra GET /me y productos/pedidos **200**, un único POST /pedidos **201**, Admin **403** dos veces y los rechazos/preflights anteriores. [RDS y access logs](rds-order-and-service-access.json) confirman UUID completo `9f82f14f-7f81-4f6a-a346-2add0865fe7f`, propietario tid+oid, total, dos snapshots y las llamadas BFF → Orders → Catalog. El POST figura a las 19:49:22 UTC en BFF/Orders; Catalog respondió por ambos productos antes de persistir.

Los GET duplicados iniciales provienen del montaje de desarrollo de React; el POST no se repitió. Los logs capturados contienen método/ruta/estado/duración sin Authorization, query ni cuerpo.

## Límites explícitos

No se inició sesión real con Jazmín y no se asignó Admin temporal durante FASE 5/6. Se conserva su asignación permanente verificada en Graph y la evidencia funcional Admin 200 de FASE 2 con asignación temporal aprobada y luego retirada. No se presenta esa prueba anterior como una sesión Admin en AWS. Los casos criptográficos adversos y scopes controlados se cubren en los tests Java/locales; no se declara haber obtenido de Microsoft un token real con cada claim adverso. GET individuales por ID tienen cobertura de contrato/local y ruta cloud configurada; la SPA de esta prueba recuperó el pedido mediante el listado propio.
