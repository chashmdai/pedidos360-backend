"""Public, verified Entra configuration. No credentials or access tokens are stored here."""
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse
from uuid import UUID

ROOT = Path(__file__).resolve().parent.parent


def environment(cloud=False):
    config = json.loads((ROOT / "config/entra-public.json").read_text())
    tenant, api, spa = (str(UUID(config[key])) for key in ("tenantId", "apiClientId", "spaClientId"))
    scopes = config["scopes"]
    if scopes != ["Catalog.Read", "Orders.Read", "Orders.Create"]:
        raise ValueError("Entra scopes differ from the approved HTTP security contract")
    base_url = "http://127.0.0.1:8180/api/v1"
    if cloud:
        aws = json.loads((ROOT / "config/aws-public.json").read_text())
        base_url = aws["apiBaseUrl"]
        url = urlparse(base_url)
        if aws["account"] != "002996184293" or aws["region"] != "us-east-1" or url.scheme != "https" or url.hostname != f"{aws['apiId']}.execute-api.us-east-1.amazonaws.com" or url.path != "/api/v1" or url.query or url.fragment:
            raise ValueError("Cloud frontend must use the verified Pedidos360 HTTP API")
    return {
        "JWT_TENANT_ID": tenant, "JWT_AUDIENCE": api, "JWT_CLIENT_ID": spa,
        "JWT_ISSUER": f"https://login.microsoftonline.com/{tenant}/v2.0",
        "JWT_JWKS_URI": f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys",
        "VITE_AUTH_MODE": "entra", "VITE_AZURE_TENANT_ID": tenant, "VITE_AZURE_CLIENT_ID": spa,
        "VITE_API_SCOPES": " ".join(f"api://{api}/{scope}" for scope in scopes),
        "VITE_API_BASE_URL": base_url,
        "SPRING_PROFILES_ACTIVE": "entra",
    }


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("frontend", "frontend-cloud", "backend"):
        raise SystemExit("Usage: python3 scripts/entra_config.py frontend|frontend-cloud|backend command [args...]")
    cwd = ROOT.parent / "pedidos360-frontend" if sys.argv[1].startswith("frontend") else ROOT
    raise SystemExit(subprocess.call(sys.argv[2:], cwd=cwd, env={**os.environ, **environment(cloud=sys.argv[1] == 'frontend-cloud')}))
