# Lectura IAM inicial — 2026-09-06

Observación conservada del resultado de la herramienta antes de retomar el inventario; no se repitió la consulta denegada.

Comando: `aws iam get-role --role-name voclabs --query 'Role.{Name:RoleName,Arn:Arn,PermissionsBoundary:PermissionsBoundary}' --output json --no-cli-pager`.

Error devuelto (texto del diagnóstico):

```text
aws: [ERROR]: An error occurred (AccessDenied) when calling the GetRole operation: User: arn:aws:sts::002996184293:assumed-role/voclabs/user3301432=BENJAMIN__TORREJON is not authorized to perform: iam:GetRole on resource: role voclabs with an explicit deny in an identity-based policy: arn:aws:iam::002996184293:policy/Pvoclabs2.
```

La respuesta también incluía un enlace de diagnóstico de autorización, que no se abrió. No se intentó GetRequestAuthorizationDetails ni modificar políticas. El código de salida individual no quedó capturado en ese bloque de tres comandos; no se inventa un valor.

Las siguientes lecturas sí respondieron: `list-attached-role-policies` para voclabs devolvió Pvoclabs1, Pvoclabs2 y voc-cancel-cred; `list-role-policies` devolvió una lista vacía. Los intentos de leer GetPolicy están guardados por separado con su código y error exactos. El perfil LabInstanceProfile y sus políticas de rol se inspeccionaron después como recursos distintos, no para eludir el deny sobre voclabs.
