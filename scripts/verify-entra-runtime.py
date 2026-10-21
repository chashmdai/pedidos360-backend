"""Read-only HTTP checks against the actual Entra-configured local processes. No real tokens required."""
import json
from pathlib import Path
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from entra_config import environment

ROOT = Path(__file__).resolve().parent.parent
config = environment()
results = []


def call(port, path, expected, method="GET", headers=None):
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method, headers=headers or {})
    try:
        response = urllib.request.urlopen(request, timeout=20)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        status = response.status
        result = {"port": port, "method": method, "path": path, "expected": expected, "actual": status}
        results.append(result)
        assert status == expected, result
        return response.headers


with urllib.request.urlopen(config["JWT_ISSUER"] + "/.well-known/openid-configuration", timeout=20) as response:
    discovery = json.load(response)
assert discovery["issuer"] == config["JWT_ISSUER"]
assert discovery["jwks_uri"] == config["JWT_JWKS_URI"]
with urllib.request.urlopen(discovery["jwks_uri"], timeout=20) as response:
    assert json.load(response)["keys"], "Entra JWKS must publish signing keys"

# Deliberately reject the Phase 1 local signer in actual Entra mode; never print its bearer.
fixture = subprocess.check_output(["node", "scripts/local-identity.mjs", "token"], cwd=ROOT, text=True)
for port, paths in [(8180, ["/api/v1/me", "/api/v1/productos", "/api/v1/pedidos", "/api/v1/admin/pedidos"]),
                    (8181, ["/api/v1/productos"]), (8182, ["/api/v1/pedidos", "/api/v1/admin/pedidos"])]:
    call(port, "/actuator/health", 200)
    for path in paths:
        call(port, path, 401)
        call(port, path, 401, headers={"Authorization": "Bearer invalid.jwt.value"})
    call(port, paths[0], 401, headers={"Authorization": "Bearer " + fixture})
    results[-1]["case"] = "local_fixture_rejected_in_entra_mode"

for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
    headers = call(8180, "/api/v1/me", 200, "OPTIONS", {
        "Origin": origin, "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization,content-type",
    })
    assert headers["Access-Control-Allow-Origin"] == origin
call(8180, "/api/v1/me", 403, "OPTIONS", {
    "Origin": "https://untrusted.invalid", "Access-Control-Request-Method": "GET",
    "Access-Control-Request-Headers": "authorization",
})
report = {"at": datetime.now(timezone.utc).isoformat(), "mode": "entra", "discovery_and_jwks_verified": True,
          "note": "No valid Entra access token used here. Real authenticated browser evidence is separate.",
          "checks": results, "passed": len(results)}
destination = ROOT / "docs/evidence/phase2/entra-runtime-http.json"
destination.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
