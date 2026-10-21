# Approved change: append only the cloud SPA redirect, preserving all other settings.
$ErrorActionPreference = 'Stop'
$ep4Root = Split-Path -Parent $PSScriptRoot
$ep4Out = Join-Path $ep4Root 'docs/evidence/ep4'
$ep4Client = 'b4ede06a-cde3-4982-8b79-56fab7264fdd'
$ep4Uri = 'https://7k2zyh0t0d.execute-api.us-east-1.amazonaws.com/app/'
$ep4Query = '{objectId:id,appId:appId,displayName:displayName,spa:spa,api:api,roles:appRoles,permissions:requiredResourceAccess}'
$ep4BeforeJson = az ad app show --id $ep4Client --query $ep4Query -o json
if ($LASTEXITCODE -ne 0) { throw 'Entra read failed; authenticate manually, no write attempted.' }
$ep4Before = $ep4BeforeJson | ConvertFrom-Json
if ($ep4Before.objectId -ne 'fbfdd96f-b7f0-4fd6-8763-f698a1d5f43e') { throw 'Unexpected application object.' }
$ep4BeforeJson | Set-Content -LiteralPath (Join-Path $ep4Out 'entra-spa-before.json')
if ($ep4Uri -notin $ep4Before.spa.redirectUris) {
    $ep4Payload = @{spa = @{redirectUris = @($ep4Before.spa.redirectUris) + @($ep4Uri)}} | ConvertTo-Json -Depth 8
    $ep4Temp = [IO.Path]::GetTempFileName()
    try {
        [IO.File]::WriteAllText($ep4Temp, $ep4Payload)
        az rest --method PATCH --url ('https://graph.microsoft.com/v1.0/applications/' + $ep4Before.objectId) --headers 'Content-Type=application/json' --body ('@' + $ep4Temp) --output none
        if ($LASTEXITCODE -ne 0) { throw 'Approved redirect PATCH failed; stop without changing permissions.' }
    } finally { Remove-Item -LiteralPath $ep4Temp }
}
$ep4AfterJson = az ad app show --id $ep4Client --query $ep4Query -o json
if ($LASTEXITCODE -ne 0) { throw 'Read-back failed; inspect before any retry.' }
$ep4After = $ep4AfterJson | ConvertFrom-Json
$ep4AfterJson | Set-Content -LiteralPath (Join-Path $ep4Out 'entra-spa-after.json')
if ($ep4Uri -notin $ep4After.spa.redirectUris) { throw 'Redirect not verified.' }
foreach ($ep4Field in @('api','roles','permissions')) {
    if (($ep4Before.$ep4Field | ConvertTo-Json -Depth 20 -Compress) -ne ($ep4After.$ep4Field | ConvertTo-Json -Depth 20 -Compress)) { throw ('Unexpected change: '+$ep4Field) }
}
Write-Output 'Cloud redirect verified; previous redirects, roles, scopes and API permissions preserved.'
