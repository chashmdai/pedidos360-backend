"""Public HTTP probes through API Gateway only (no tokens or browser sessions are read): SPA bytes must match
the release manifest; protected routes, including EP5 GET /api/v1/ventas/en-vivo, must answer 401."""
import datetime as dt
import hashlib
import json
import re
import urllib.error
import urllib.request
import aws_deploy as aws

base = json.loads((aws.ROOT / "config/aws-public.json").read_text())["apiEndpoint"]
manifest = json.loads((aws.EVIDENCE / "release-manifest.json").read_text())
report = {"at": dt.datetime.now(dt.timezone.utc).isoformat(), "endpoint": base, "release": manifest["release"], "checks": []}

def probe(path, expected, bearer=None):
    headers = {"Authorization": "Bearer " + bearer} if bearer else {}
    try:
        response = urllib.request.urlopen(urllib.request.Request(base + path, headers=headers), timeout=20)
    except urllib.error.HTTPError as error:
        response = error
    body = response.read()
    check = {"path": path, "status": response.code, "expected": expected, "syntheticInvalidBearer": bool(bearer),
             "requestId": response.headers.get("apigw-requestid"), "contentType": response.headers.get("Content-Type"),
             "sha256": hashlib.sha256(body).hexdigest()}
    report["checks"].append(check)
    assert response.code == expected, check
    return body

html = probe("/app/", 200).decode()
probe("/app", 200)
probe("/app/ventas-en-vivo", 200)
for asset in re.findall(r'(?:src|href)="(/app/assets/[^" ]+)"', html):
    data = probe(asset, 200)
    assert hashlib.sha256(data).hexdigest() == manifest["files"]["frontend/" + asset.removeprefix("/app/")], asset
    if asset.endswith(".js"):
        assert b"127.0.0.1:8190" not in data, "local JWT fixture must not be in the production bundle"
        assert base.encode() in data, "bundle must target the new HTTP API"
for path in ("/api/v1/productos", "/api/v1/pedidos", "/api/v1/me", "/api/v1/ventas/en-vivo"):
    probe(path, 401)
    probe(path, 401, bearer="invalid-ep5-probe")
report["frontendBytesMatchRelease"] = True
(aws.EVIDENCE / "gateway-http.json").write_text(json.dumps(report, indent=2) + "\n")
for c in report["checks"]:
    print(f"{c['status']} (expected {c['expected']}) {c['path']}{' [invalid bearer]' if c['syntheticInvalidBearer'] else ''}")
