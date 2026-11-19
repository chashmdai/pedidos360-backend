"""EP5 Fase 5: add the new /app/ redirect URI to the SPA, keeping the existing ones. Before/after reads as evidence."""
import datetime as dt, json, subprocess, sys
APP = "b4ede06a-cde3-4982-8b79-56fab7264fdd"; OBJ = "fbfdd96f-b7f0-4fd6-8763-f698a1d5f43e"
NEW = "https://az3h2vqgsi.execute-api.us-east-1.amazonaws.com/app/"
KEEP = ["https://7k2zyh0t0d.execute-api.us-east-1.amazonaws.com/app/", "http://127.0.0.1:5173/", "http://localhost:5173/"]
OUT = "docs/evidence/ep5"
def read():
    r = subprocess.run(["az", "rest", "--method", "GET", "--url",
        f"https://graph.microsoft.com/v1.0/applications/{OBJ}?$select=appId,id,displayName,spa,web,publicClient,signInAudience"],
        capture_output=True, text=True, check=True)
    d = json.loads(r.stdout); d.pop("@odata.context", None)
    assert d["appId"] == APP
    return {"at": dt.datetime.now(dt.timezone.utc).isoformat(), "application": d}
before = read(); json.dump(before, open(f"{OUT}/entra-spa-before.json", "w"), indent=2)
current = before["application"]["spa"]["redirectUris"]
assert all(u in current for u in KEEP), "An expected existing URI is missing; stop"
target = current + ([NEW] if NEW not in current else [])
if target != current:
    body = json.dumps({"spa": {"redirectUris": target}})
    subprocess.run(["az", "rest", "--method", "PATCH", "--url", f"https://graph.microsoft.com/v1.0/applications/{OBJ}",
                    "--headers", "Content-Type=application/json", "--body", body], check=True, capture_output=True)
after = read(); json.dump(after, open(f"{OUT}/entra-spa-after.json", "w"), indent=2)
uris = after["application"]["spa"]["redirectUris"]
assert NEW in uris and all(u in uris for u in KEEP) and len(uris) == 4, uris
print(json.dumps({"before": current, "after": uris, "changed": target != current}, indent=1))
