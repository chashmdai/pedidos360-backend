# Pruebas y evidencias reproducibles

Ejecutar desde WSL con Java 25, Maven Linux y acceso al socket Docker Linux.

```bash
mvn clean verify
```

| Suite | Cobertura |
|---|---|
| CatalogIntegrationTest | MySQL real, Flyway + seed, representación HTTP, JWT ausente/malformado/firma alterada/issuer/audience/expiración y scopes |
| OrderDomainTest | Cálculo decimal multítem, inmutabilidad, cantidades/monedas válidas y ausencia de escritura parcial ante fallo del puerto Catalog |
| OrdersIntegrationTest | MySQL real, Flyway, snapshots, propietario, cabecera/líneas, precisión de fecha, validación de cuerpo/scopes y consulta Admin separada de propietario/tenant |
| BffContractTest | HTTP real, reenvío de body/bearer/Location/código de estado, /me, no-store, rol+scope Admin, ausencia de expiración/audience, tenant/cliente/versión/nbf y firma |

Testcontainers 2.0.5 inicia una instancia MySQL 8.4.11 efímera por contexto en puertos dinámicos. Las pruebas no dependen de Compose ni de datos ajenos y no usan H2. Catalog/Orders se integran con una base real; el test de Orders sustituye Catalog por un servidor HTTP controlado para demostrar cambios de precio. `verify-local.py` completa la comprobación con los tres servicios reales.

Los contenedores y redes de pruebas se llaman `pedidos360-test-*` y tienen las etiquetas `Project=Pedidos360`, `Purpose=test`. Se cierran en `@AfterAll` y también si falla el inicio del contenedor. Ryuk se deshabilita solo en el proceso Surefire para mantener todos los recursos con identificación Pedidos360; no se modifica la configuración global de Docker/Testcontainers. Esto pierde la limpieza externa de Ryuk si la JVM termina abruptamente. Ante un fallo así, revisar primero `docker ps -a --filter label=Project=Pedidos360 --filter label=Purpose=test` y las redes con esas etiquetas; nunca ejecutar limpieza global. [Configuración oficial de Testcontainers](https://java.testcontainers.org/features/configuration/).

```bash
bash scripts/dev.sh start local # requiere haber detenido antes el modo Entra
python3 scripts/verify-local.py
python3 scripts/verify-database.py
bash scripts/mysql.sh ps
```

`verify-local.py` ejecuta 51 comprobaciones HTTP y crea un pedido de prueba con propietario `phase1-verification`. Primero comprueba que el runtime usa el fixture local. Comprueba total de 30970 CLP, dos líneas, persistencia, listados propios y rechazos JWT en los tres procesos. En BFF y Orders prueba Admin Y Orders.Read, denegación a User, scope insuficiente y aislamiento de los endpoints propios incluso para Admin. Registra método, ruta, esperado y recibido. Obtiene JWT únicamente en memoria y no los imprime. Repetirlo crea otro pedido de prueba.

`verify-database.py` consulta únicamente `pedidos360-mysql`: versión, historial Flyway, lectura del esquema propio, rechazo 1142 al otro contexto y rechazo DDL con usuarios de aplicación. Lee secretos dentro del contenedor, sin mostrarlos.

Frontend: `npm run build` y `npm test` desde el repositorio hermano. El build verifica TypeScript y Vite; Vitest cubre adquisición del bearer, petición de creación, tratamiento de 403 y rechazo de destinos externos en el cliente API. MSAL tiene además pruebas de access token frente a ID token, scopes exactos, forceRefresh, selección de cuenta, logout y fallback exclusivo para InteractionRequiredAuthError. Las pruebas controladas no sustituyen la evidencia de navegador real de `docs/evidence/phase2/`.

Maven Wrapper fija 3.9.16 e incorpora SHA-256 de la distribución, validada previamente contra SHA-512 de Maven Central. [Documentación oficial del wrapper](https://maven.apache.org/tools/wrapper/).

Las evidencias iniciales se conservan en `docs/evidence/` y `FASE_1.md` del workspace. Las verificaciones posteriores están en `docs/evidence/phase2/`, `docs/evidence/phase3/` y los informes FASE_2/FASE_3 del workspace. Los logs de ejecución completos quedan fuera de Git, en `~/.local/state/pedidos360-phase1/`; los extractos HTTP revisados se conservan como `.txt`.

## FASE 2: identidad real frente a fixtures

`docs/evidence/entra/` conserva la creación aprobada y lecturas posteriores, más el Admin temporal aprobado y su retirada. No repetir esas escrituras al ejecutar tests. `docs/evidence/phase2/browser-user.md` registra User real; `browser-admin-temporary.md` registra la variante de Admin temporal. No se autenticó a Jazmín.

`browser-final.md` cierra la evidencia: token nuevo desde Microsoft sin Admin, 403 administrativo y logout con retorno automático. Las cinco rutas protegidas redirigieron al inicio en esa misma pestaña después del logout. La sesión real de Jazmín permanece no ejecutada por disponibilidad de credenciales/MFA; el usuario aceptó este límite.

Con los servicios en modo Entra:

```bash
python3 scripts/verify-entra-runtime.py
```

La batería comprueba 23 estados HTTP, discovery y JWKS oficiales. No obtiene tokens válidos de Microsoft: prueba salud, rechazos y CORS. Los positivos con token real se observan en el navegador y se contrastan con los access logs de BFF/Catalog/Orders.

Los access logs generados por el launcher contienen únicamente fecha, método, ruta sin query, estado y duración. Nunca contienen Authorization, query strings, cuerpos ni secretos. La emisión/expiración y roles visibles en Mi sesión provienen del BFF; los JWT no se copian al repositorio.

Renovar sesión significa solicitar forceRefresh a Microsoft, no esperar la expiración natural. Retirar una asignación de rol no invalida retroactivamente un bearer ya emitido; se necesita un token nuevo y puede existir demora de propagación de claims. No se alteran políticas del tenant para acelerar las pruebas.

## FASE 5/6: pruebas reales en AWS

[Instalación verificada](evidence/phase5/runtime-verification.json): los tres JAR coinciden con el manifiesto, salud 200, MySQL 8.4.11 con TLS/hostname/CA verificados, Flyway Catalog V1/V2 y Orders V1, usuarios aislados y privilegios DDL denegados. La reanudación tras reiniciar el laboratorio corrigió el modo de una carpeta de release; no repitió creación ni provisión SQL.

`python3 scripts/verify-cloud-http.py` ejecutó 19 checks contra el endpoint HTTPS real: siete rutas rechazaron bearer ausente y malformado, el fixture local fue rechazado, Actuator no está publicado y CORS permitió únicamente los orígenes aprobados. CORS de HTTP API devuelve 204 sin Allow-Origin para el origen ajeno; no se inventa un 403 en ese caso.

Diez requests por loopback dentro de EC2 verificaron rechazo 401 independiente del Gateway en BFF, Catalog y Orders: [evidencia](evidence/phase6/cloud-processes-security.json). Los casos criptográficos/scopes adversos detallados siguen respaldados por los tests Java/locales; no se emitieron tokens Microsoft falsos para simularlos.

[Navegador cloud](evidence/phase6/browser-e2e.md): User real, catálogo, creación 201 de dos líneas por 30.970 CLP, recuperación tras recargar, Admin 403, forceRefresh desde Microsoft, logout y cinco rutas anónimas protegidas. [CloudWatch](evidence/phase6/gateway-access-events.json) y [RDS/access logs](evidence/phase6/rds-order-and-service-access.json) acreditan el recorrido y el mismo UUID. No se inició sesión Admin con Jazmín durante cloud ni se volvió a asignar Admin temporal.

La [auditoría de infraestructura](evidence/phase5/infrastructure-audit.json) pasó 20 checks de tamaños, cifrado, JWT, CORS, rutas y aislamiento; incluye sondas TCP desde el operador a cinco puertos de la EC2 tras cerrar SSH. [Checklist final](CHECKLIST_FINAL.md) mapea los resultados a la pauta y explicita los límites de la evidencia.
