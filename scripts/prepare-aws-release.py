"""Prepare a private deployment directory in WSL; build and inspect AWS first."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "docs/evidence/phase5"
PRIVATE = Path.home() / ".config/pedidos360/aws"
os.umask(0o077)
status = json.loads((EVIDENCE / "status-latest.json").read_text())
rds = status["rds"]["DBInstances"][0]
if rds["DBInstanceIdentifier"] != "pedidos360-mysql" or rds["DBInstanceStatus"] != "available":
    raise SystemExit("Inspect AWS: the dedicated RDS must be available before preparing the release")
instance = status["ec2"]["Reservations"][0]["Instances"][0]
if not any(t["Key"] == "Project" and t["Value"] == "Pedidos360" for t in instance["Tags"]):
    raise SystemExit("Unrecognized deployment target")
release_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
directory = PRIVATE / "releases" / release_id
directory.mkdir(parents=True, mode=0o700)
artifacts = {}
for module in ("catalog-service", "orders-service", "bff"):
    source = ROOT / module / "target" / f"{module}-0.1.0-SNAPSHOT.jar"
    target = directory / (module + ".jar")
    shutil.copyfile(source, target)
    artifacts[target.name] = hashlib.sha256(target.read_bytes()).hexdigest()
deployment = {"release": release_id, "rdsEndpoint": rds["Endpoint"]["Address"], "instanceId": instance["InstanceId"], "publicIp": instance["PublicIpAddress"], "artifacts": artifacts, "entra": json.loads((ROOT / "config/entra-public.json").read_text())}
(directory / "deployment.json").write_text(json.dumps(deployment, indent=2) + "\n")
passwords = {name: (PRIVATE / (name + "-password")).read_text().strip() for name in ("master", "catalog-app", "catalog-migration", "orders-app", "orders-migration")}
(directory / "secrets.json").write_text(json.dumps(passwords))
(directory / "secrets.json").chmod(0o600)
shutil.copyfile(ROOT / "deploy/install-release.py", directory / "install-release.py")
(PRIVATE / "current-release").write_text(str(directory) + "\n")
(EVIDENCE / "release-manifest.json").write_text(json.dumps(deployment, indent=2) + "\n")
print(f"Prepared release {release_id}; 3 JAR checksums recorded. Secrets stored outside Git.")
