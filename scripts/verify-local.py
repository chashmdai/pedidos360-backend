"""Execute the local HTTP slice. JWTs stay in memory and are never printed."""
import json
from pathlib import Path
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
checks = []


def token(**options):
    return subprocess.check_output(["node", str(ROOT / "scripts/local-identity.mjs"), "token", json.dumps(options)], text=True)


def call(port, path, bearer=None, body=None):
    headers = {"Content-Type": "application/json"}
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as response:
        return response.code, None


def expect(label, port, path, status, bearer=None, body=None):
    actual, payload = call(port, path, bearer, body)
    if actual != status:
        raise AssertionError(f"{label}: expected {status}, received {actual}")
    checks.append({"check": label, "port": port, "method": "POST" if body is not None else "GET",
                   "path": path, "expected": status, "actual": actual})
    return payload


for port in [8180, 8181, 8182]:
    expect("actuator health", port, "/actuator/health", 200)
owner = token(subject="phase1-verification")
# Fail before creating data if the running processes are not explicitly in fixture mode.
identity = expect("local fixture identity", 8180, "/api/v1/me", 200, owner)
assert identity["issuer"] == "http://127.0.0.1:8190" and identity["tenantId"] == "local-development"
products = expect("Catalog direct", 8181, "/api/v1/productos", 200, owner)
assert len(products) == 2
assert products == expect("Catalog through BFF", 8180, "/api/v1/productos", 200, owner)
for port, path, unrelated_scope in [(8180, "/api/v1/productos", "Orders.Read"),
                                     (8181, "/api/v1/productos", "Orders.Read"),
                                     (8182, "/api/v1/pedidos", "Catalog.Read")]:
    expect("missing token", port, path, 401)
    expect("missing scope", port, path, 403, token(scopes=unrelated_scope))
    expect("wrong audience", port, path, 401, token(audience="wrong"))
    expect("wrong issuer", port, path, 401, token(issuer="https://wrong.invalid"))
    expect("expired token", port, path, 401, token(ttl=-300))
    header, payload, signature = owner.split(".")
    invalid = header + "." + payload + "." + ("A" if signature[0] != "A" else "B") + signature[1:]
    expect("invalid signature", port, path, 401, invalid)
created = expect("multitem order through BFF", 8180, "/api/v1/pedidos", 201, owner,
                 {"items": [{"productoId": products[0]["id"], "cantidad": 2}, {"productoId": products[1]["id"], "cantidad": 1}]})
assert created["total"] == 30970 and len(created["items"]) == 2 and created["estado"] == "REGISTERED"
path = "/api/v1/pedidos/" + created["id"]
assert created == expect("persisted order direct", 8182, path, 200, owner)
assert created == expect("persisted order through BFF", 8180, path, 200, owner)
for port in (8180, 8182):
    expect("other owner cannot read order", port, path, 404, token(subject="another-user"))
    own_orders = expect("list owns persisted order", port, "/api/v1/pedidos", 200, owner)
    assert created in own_orders
    expect("create requires catalog scope", port, "/api/v1/pedidos", 403, token(scopes="Orders.Create"), {"items": []})
    expect("create requires orders scope", port, "/api/v1/pedidos", 403, token(scopes="Catalog.Read"), {"items": []})
    expect("invalid body", port, "/api/v1/pedidos", 400, owner, {"items": [None]})
    expect("User cannot administer", port, "/api/v1/admin/pedidos", 403, owner)
    expect("Admin still requires read scope", port, "/api/v1/admin/pedidos", 403,
           token(roles=["Admin"], scopes="Catalog.Read"))
    admin = token(subject="phase3-admin", roles=["Admin"], scopes="Orders.Read")
    all_orders = expect("Admin and read scope can administer", port, "/api/v1/admin/pedidos", 200, admin)
    assert created in all_orders
    admin_own = expect("Admin own list does not include another owner's order", port, "/api/v1/pedidos", 200, admin)
    assert created["id"] not in {order["id"] for order in admin_own}
    expect("Admin own endpoint preserves ownership", port, path, 404, admin)

for port in (8180, 8181):
    item = expect("catalog product by id", port, "/api/v1/productos/" + products[0]["id"], 200, owner)
    assert item == products[0]
    expect("unknown catalog product", port, "/api/v1/productos/00000000-0000-0000-0000-000000000000", 404, owner)

print(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "mode": "local_fixture",
                  "note": "Test RSA signer, not Microsoft identity. Runs only against local Pedidos360 ports.",
                  "result": "PASS", "passed": len(checks), "checks": checks,
                  "created_order": {"id": created["id"], "items": 2, "total": created["total"], "currency": created["moneda"]}}, indent=2))
