# Alternativa de verificación Admin — aprobada el 2026-09-06

El usuario autorizó expresamente sustituir la prueba con Jazmín por Admin temporal y retirarlo al terminar. La creación devolvió la asignación `66Z1wyq49kSr4P4y15AcPvvpgMerYCZPnZlrBkgQDMc`; sus datos están en `../evidence/entra/09-temporary-admin.response.json`. El token real mostró Admin+User y la consulta administrativa respondió 200. La asignación temporal se retiró el 2026-09-06 a las 04:32:26 UTC. Graph confirmó que las dos asignaciones originales permanecen exactamente iguales; ver `../evidence/entra/10-removal-verification.json`.

El usuario informó que no tiene la contraseña de ja.pissani@duocuc.cl. No se solicita esa contraseña, no se modifica esa identidad y no se altera su asignación Admin ya aprobada.

Se propone sustituir la prueba real de dos cuentas por una prueba de la misma cuenta en dos estados de autorización: User, ya verificado con 403, y User+Admin temporal, para comprobar 200. La identidad titular será be.torrejons@duocuc.cl. El informe distinguirá esta variante de un login real con Jazmín, que no se habrá probado.

Operaciones exactas, solo después de aprobación explícita:

1. Verificar cuenta/tenant, recurso propio y asignaciones existentes. Si Admin ya existe para Benjamin, no crear ni borrar esa asignación preexistente.
2. `POST https://graph.microsoft.com/v1.0/servicePrincipals/6a0b43df-3afe-4b55-adac-e62ea93494ff/appRoleAssignedTo` con body `09-temporary-admin-proposal.json`. Guardar el ID devuelto, si se crea.
3. Renovar el token con MSAL/reautenticar y comprobar el rol Admin real, HTTP 200 en la consulta administrativa y creación/lectura autorizadas. La asignación User permanece.
4. `DELETE https://graph.microsoft.com/v1.0/servicePrincipals/6a0b43df-3afe-4b55-adac-e62ea93494ff/appRoleAssignedTo/{id-devuelto-en-paso-2}` únicamente para la asignación temporal recién creada. Antes, verificar resourceId, principalId y appRoleId del objeto.
5. Leer de nuevo las asignaciones y obtener un token nuevo para confirmar retorno a User y 403. Los JWT ya emitidos pueden conservar Admin hasta expirar; no se afirma revocación inmediata. Cerrar la sesión temporal y no guardar esos tokens.

Esto concedió exclusivamente un rol dentro de Pedidos360. No requirió roles de directorio, cambios de políticas, credenciales nuevas ni uso de AWS. No hubo errores Graph. No repetir el POST ni el DELETE: la asignación temporal ya fue creada, probada y retirada.
