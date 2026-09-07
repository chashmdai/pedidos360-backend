# Entrega Pedidos360 — DSY1107

Repositorios de la estructura aprobada:

- [Backend: chashmdai/pedidos360-backend](https://github.com/chashmdai/pedidos360-backend): Maven multimódulo, BFF, Catalog y Orders, configuración, migraciones, contratos, scripts, documentación y evidencias.
- [Frontend: chashmdai/pedidos360-frontend](https://github.com/chashmdai/pedidos360-frontend): React, TypeScript, Vite, MSAL y diseño visual manual conservado.

La revisión local final no ejecutó operaciones AWS: el usuario informó que el laboratorio está apagado. Las evidencias cloud son registros fechados de las pruebas realizadas antes de ese aviso. No se infiere disponibilidad actual ni eliminación de los recursos.

## Lectura para evaluar

1. [README](../README.md): funcionalidad, stack y ejecución local.
2. [Arquitectura](ARQUITECTURA.md): componentes, límites de dominio, JWT, datos propios y evolución.
3. [Despliegue y reanudación](DEPLOY.md): configuración real, journal y manejo de una interrupción sin duplicar recursos.
4. [Pruebas](PRUEBAS.md) y [checklist de pauta](CHECKLIST_FINAL.md): matriz de evidencia y límites explícitos.
5. [Flujo real cloud](evidence/phase6/browser-e2e.md), [Gateway](evidence/phase6/gateway-access-events.json), [pedido en RDS](evidence/phase6/rds-order-and-service-access.json).

## Evidencia principal

- Build Maven con 13 pruebas aprobadas y MySQL real/Testcontainers; tres JAR desplegados con SHA-256 comprobado.
- Build frontend y 10 pruebas aprobadas; el CSS manual mantiene el mismo SHA-256.
- Tres servicios saludables, RDS MySQL 8.4.11 con TLS verificado, migraciones e identidades DB aisladas.
- 19 comprobaciones públicas de JWT/CORS, 10 rechazos JWT directamente en los procesos cloud y 20 comprobaciones de infraestructura.
- Login User real, GET 200, POST 201 de un pedido multítem por 30.970 CLP, recuperación después de recargar, Admin 403, token renovado aceptado, logout y cinco rutas protegidas.
- Revisión de archivos versionables sin coincidencias de secretos conocidos, claves privadas, JWT completos ni AWS access keys; Python/Bash/JSON y enlaces internos revisados.

El límite aceptado permanece: no se inició sesión real con Jazmín por disponibilidad de credenciales/MFA. Su rol Admin se verificó en Graph; el comportamiento Admin 200 se probó con la asignación temporal aprobada en FASE 2 y luego retirada. No se declara un Admin 200 cloud que no ocurrió.

Para una nueva demostración AWS, primero el usuario debe activar/renovar el laboratorio. Después corresponde STS y reconciliación de IDs, no recreación de infraestructura. Para la demostración local, seguir README/DEPLOY con WSL y el MySQL Docker exclusivo de Pedidos360. No hay nuevas App Registrations, AWS adicional, envío de correo ni entrega AVA implícitos en este cierre.
