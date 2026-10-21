> Checkpoint aprobado y ejecutado el 2026-09-05. Estos JSON conservan los cuerpos revisados; las solicitudes resueltas, respuestas y verificaciones están en `../evidence/entra/`. No volver a ejecutar las creaciones.

# Manifiestos propuestos de Microsoft Entra

**Pendientes de aprobación. No enviados a Microsoft Graph.** El checkpoint completo está en `FASE_2_CHECKPOINT.md`, en la raíz del workspace.

Los archivos 01–08 son los cuerpos de las solicitudes listadas en ese checkpoint. `{{API_CLIENT_ID}}`, `{{SPA_CLIENT_ID}}`, `{{APP_CLIENT_ID}}` y `{{API_SERVICE_PRINCIPAL_OBJECT_ID}}` son marcadores explícitos. Se resolverán con las respuestas de creación, nunca con IDs de aplicaciones ajenas. Ningún archivo contiene credenciales.

- 01 crea la API lógica, expone tres scopes y define User/Admin.
- 02 fija su Application ID URI usando su client ID real.
- 03 crea la SPA con redirects locales y permisos delegados hacia la nueva API.
- 04 crea el service principal correspondiente a cada nueva aplicación.
- 05 añade como propietario a la cuenta autenticada elegida, si aún no figura.
- 06 preautoriza exclusivamente esa SPA para los tres scopes; conservar todos los scopes al aplicar la colección.
- 07 asigna User a `be.torrejons@duocuc.cl` en la nueva API.
- 08 asigna Admin de Pedidos360 a `ja.pissani@duocuc.cl` en la nueva API.

Después de la aprobación, el formato de comando será:

```powershell
# Ejemplo de mecanismo; no ejecutado. Usar únicamente cuerpos e IDs aprobados.
az rest --method POST --url 'https://graph.microsoft.com/v1.0/applications' --body '@01-api-create.json' --headers 'Content-Type=application/json'
```

La creación de aplicaciones, la configuración de sus permisos, el consentimiento y las asignaciones tienen permisos diferentes. Que una lectura funcione o que `allowedToCreateApps=true` no garantiza cada escritura. Una denegación se documentará sin cambiar políticas ni intentar elevar privilegios.
