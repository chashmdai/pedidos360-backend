"""Package the EP5 release: 8 verified JARs, the /app/ SPA build, Compose/broker files and the reviewed
installer, with a public SHA-256 manifest. Database secrets travel in a separate private file inside the
archive (mode 0600, private directory 0700) and the installer deletes its copy after use. Read-only on AWS.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile
import aws_deploy as aws

ROOT = aws.ROOT
BUILD = ROOT / "docs/evidence/ep5/build"
MODULES = ("catalog-service", "orders-service", "bff", "receipts-service", "rabbit-admin-service",
           "order-insights-service", "sales-stream-service", "kafka-admin-service")
FILES = ("compose.ep4.yaml", "docker/rabbitmq/ep4-entrypoint.sh", "docker/rabbitmq/ep4.conf", "scripts/ep4-broker.py",
         "messaging-support/src/main/resources/pedidos-rabbit.properties",
         "compose.kafka.yaml", "compose.kafka-ui.yaml", "scripts/ep5-kafka.sh",
         "kafka-support/src/main/resources/pedidos-kafka.properties", "deploy/ep5-install.py")
SECRETS = ("master", "catalog-app", "catalog-migration", "orders-app", "orders-migration", "streams-app", "streams-migration")

os.umask(0o077)
assert "BUILD SUCCESS" in (BUILD / "backend-verify.txt").read_text(), "Run bash scripts/ep5-build.sh first"
assert "built in" in (BUILD / "frontend-build.txt").read_text(), "Run bash scripts/ep5-build.sh frontend first"
gateway = json.loads((ROOT / "config/aws-public.json").read_text())
assert gateway["account"] == aws.ACCOUNT, "config/aws-public.json does not belong to the deployment target"

identity = aws.call("sts", "get-caller-identity")
assert identity["Account"] == aws.ACCOUNT and "/voclabs/" in identity["Arn"]
state = json.loads(aws.JOURNAL.read_text())
instance_id = state["steps"]["ec2"]["response"]["Instances"][0]["InstanceId"]
rds = aws.call("rds", "describe-db-instances", {"DBInstanceIdentifier": "pedidos360-mysql"})["DBInstances"][0]
assert rds["DBInstanceStatus"] == "available" and not rds["PubliclyAccessible"], "RDS must be available and private"

release = "ep5-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
stage = aws.PRIVATE / "releases" / release
stage.mkdir(parents=True, exist_ok=False, mode=0o700)
for module in MODULES:
    shutil.copyfile(ROOT / module / "target" / f"{module}-0.1.0-SNAPSHOT.jar", stage / f"{module}.jar")
shutil.copytree(Path.home() / ".cache/pedidos360-ep5/frontend/dist", stage / "frontend")
for relative in FILES:
    target = stage / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / relative, target)
deployment = {"release": release, "account": aws.ACCOUNT, "region": aws.REGION, "instanceId": instance_id,
              "rdsEndpoint": rds["Endpoint"]["Address"], "entra": json.loads((ROOT / "config/entra-public.json").read_text()),
              "gateway": gateway}
(stage / "deployment.json").write_text(json.dumps(deployment, indent=2) + "\n")
files = {str(p.relative_to(stage)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(stage.rglob("*")) if p.is_file()}
manifest = {"release": release, "at": dt.datetime.now(dt.timezone.utc).isoformat(), "files": files}
(stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
# Private part: never listed in the public manifest, never written to Git or evidence.
(stage / "secrets.json").write_text(json.dumps({name: (aws.PRIVATE / f"{name}-password").read_text().strip() for name in SECRETS}))
(stage / "secrets.json").chmod(0o600)
archive = stage.parent / f"pedidos360-{release}.tgz"
with tarfile.open(archive, "w:gz", compresslevel=1) as tar:
    tar.add(stage, arcname=release)
archive.chmod(0o600)
manifest.update(archiveSha256=hashlib.sha256(archive.read_bytes()).hexdigest(), archiveBytes=archive.stat().st_size,
                deployment={k: v for k, v in deployment.items() if k != "entra"})
(aws.EVIDENCE / "release-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
(aws.PRIVATE / "current-bundle").write_text(str(archive) + "\n")
print(f"{archive} ({archive.stat().st_size // (1024 * 1024)} MiB, {len(files)} files with SHA-256)")
