"""Root-only installer for the dedicated Pedidos360 EC2. Private input stays off Git.

Usage: sudo python3 install-release.py /home/ubuntu/pedidos360-stage
The directory contains deployment.json, secrets.json and checksum-listed JARs.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

if os.geteuid() != 0:
    raise SystemExit("Run as root on the dedicated Pedidos360 EC2")
if not Path("/var/lib/pedidos360-provision/bootstrap-complete").exists():
    raise SystemExit("Pedidos360 bootstrap has not completed")
os.umask(0o077)
bundle = Path(sys.argv[1]).resolve()
deployment = json.loads((bundle / "deployment.json").read_text())
passwords = json.loads((bundle / "secrets.json").read_text())
endpoint = deployment["rdsEndpoint"]
if not re.fullmatch(r"pedidos360-mysql\.[a-z0-9.-]+\.us-east-1\.rds\.amazonaws\.com", endpoint):
    raise SystemExit("Unexpected RDS endpoint")
release_id = deployment["release"]
if not re.fullmatch(r"[a-zA-Z0-9-]{1,80}", release_id):
    raise SystemExit("Invalid release identifier")
for value in passwords.values():
    if not re.fullmatch(r"[0-9a-f]{32,48}", value):
        raise SystemExit("Unexpected secret format")
for name, checksum in deployment["artifacts"].items():
    if name not in ("bff.jar", "catalog-service.jar", "orders-service.jar"):
        raise SystemExit("Unexpected artifact")
    if hashlib.sha256((bundle / name).read_bytes()).hexdigest() != checksum:
        raise SystemExit("Artifact checksum mismatch: " + name)

tls = Path("/etc/pedidos360/tls")
truststore = tls / "rds-truststore.p12"
if not truststore.exists():
    certificates = re.findall(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", (tls / "rds-ca-bundle.pem").read_text(), re.S)
    if not certificates:
        raise SystemExit("Empty RDS CA bundle")
    for index, certificate in enumerate(certificates):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".crt") as temp:
            temp.write(certificate + "\n")
            temp.flush()
            subprocess.run(["/opt/pedidos360/runtime/bin/keytool", "-importcert", "-noprompt", "-alias", f"rds-{index}", "-file", temp.name, "-keystore", str(truststore), "-storetype", "PKCS12", "-storepass", "changeit"], check=True, capture_output=True)
    truststore.chmod(0o644)  # Public CA certificates, no private keys.


def mysql(user, password, sql, expected=0):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".cnf") as config:
        config.write(f"[client]\nhost={endpoint}\nport=3306\nuser={user}\npassword={password}\nssl-mode=VERIFY_IDENTITY\nssl-ca={tls}/rds-ca-bundle.pem\n")
        config.flush()
        result = subprocess.run(["mysql", "--defaults-extra-file=" + config.name, "--batch", "--raw"], input=sql, text=True, capture_output=True)
    if result.returncode != expected:
        error = result.stderr
        for secret in passwords.values():
            error = error.replace(secret, "[REDACTED]")
        raise RuntimeError(f"MySQL {user}: " + error)
    return {"exitCode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


statements = []
for context in ("catalog", "orders"):
    database = "pedidos360_" + context
    statements.append(f"CREATE DATABASE IF NOT EXISTS {database} CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;")
    for role in ("app", "migration"):
        user = f"pedidos360_{context}_{role}"
        password = passwords[f"{context}-{role}"]
        statements.append(f"CREATE USER IF NOT EXISTS '{user}'@'%' IDENTIFIED BY '{password}' REQUIRE SSL;")
        grants = "SELECT,INSERT,UPDATE,DELETE" + (",CREATE,ALTER,INDEX,DROP,REFERENCES" if role == "migration" else "")
        statements.append(f"GRANT {grants} ON {database}.* TO '{user}'@'%';")
mysql("pedidos360_master", passwords["master"], "\n".join(statements))

release = Path("/opt/pedidos360/releases") / release_id
release.mkdir(exist_ok=True, mode=0o755)
# mkdir's requested mode is filtered by umask(077); service users need traversal.
release.chmod(0o755)
for artifact in deployment["artifacts"]:
    shutil.copyfile(bundle / artifact, release / artifact)
    (release / artifact).chmod(0o644)
public_config = {k: v for k, v in deployment.items() if k != "secrets"}
(release / "manifest.json").write_text(json.dumps(public_config, indent=2) + "\n")
(release / "manifest.json").chmod(0o644)

entra = deployment["entra"]
common = {
    "SPRING_PROFILES_ACTIVE": "cloud",
    "JWT_TENANT_ID": entra["tenantId"], "JWT_AUDIENCE": entra["apiClientId"], "JWT_CLIENT_ID": entra["spaClientId"],
    "JWT_ISSUER": f"https://login.microsoftonline.com/{entra['tenantId']}/v2.0",
    "JWT_JWKS_URI": f"https://login.microsoftonline.com/{entra['tenantId']}/discovery/v2.0/keys",
    "SERVER_TOMCAT_ACCESSLOG_ENABLED": "true", "SERVER_TOMCAT_ACCESSLOG_PATTERN": "%t %m %U %s %D",
    "SERVER_TOMCAT_ACCESSLOG_BUFFERED": "false",
}
for context, artifact in (("catalog", "catalog-service.jar"), ("orders", "orders-service.jar"), ("bff", "bff.jar")):
    env = {**common, "SERVER_ADDRESS": "0.0.0.0" if context == "bff" else "127.0.0.1",
           "SERVER_TOMCAT_ACCESSLOG_DIRECTORY": f"/var/log/pedidos360/{context}"}
    if context != "bff":
        prefix = context.upper()
        url = f"jdbc:mysql://{endpoint}:3306/pedidos360_{context}?sslMode=VERIFY_IDENTITY&trustCertificateKeyStoreUrl=file:///etc/pedidos360/tls/rds-truststore.p12&trustCertificateKeyStoreType=PKCS12&trustCertificateKeyStorePassword=changeit&fallbackToSystemTrustStore=false&connectionTimeZone=UTC"
        env.update({f"{prefix}_DB_URL": url, f"{prefix}_DB_USER": f"pedidos360_{context}_app", f"{prefix}_DB_PASSWORD": passwords[context + "-app"], f"{prefix}_MIGRATION_USER": f"pedidos360_{context}_migration", f"{prefix}_MIGRATION_PASSWORD": passwords[context + "-migration"]})
    envfile = Path(f"/etc/pedidos360/{context}.env")
    envfile.write_text("".join(f'{key}="{value}"\n' for key, value in env.items()))
    envfile.chmod(0o600)
    unit = f"""[Unit]
Description=Pedidos360 {context}
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
User=pedidos360-{context}
Group=pedidos360-{context}
WorkingDirectory=/opt/pedidos360/current
EnvironmentFile=/etc/pedidos360/{context}.env
ExecStart=/opt/pedidos360/runtime/bin/java --enable-native-access=ALL-UNNAMED -Djava.net.preferIPv4Stack=true -Xms64m -Xmx384m -jar /opt/pedidos360/current/{artifact}
Restart=on-failure
RestartSec=10
TimeoutStopSec=40
SuccessExitStatus=143
UMask=0027
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/log/pedidos360/{context}

[Install]
WantedBy=multi-user.target
"""
    unitfile = Path(f"/etc/systemd/system/pedidos360-{context}.service")
    unitfile.write_text(unit)
    unitfile.chmod(0o644)

current = Path("/opt/pedidos360/current")
if current.exists() and current.resolve() != release:
    previous = Path("/opt/pedidos360/previous")
    previous.unlink(missing_ok=True)
    previous.symlink_to(current.resolve())
temporary_link = Path("/opt/pedidos360/current.next")
temporary_link.unlink(missing_ok=True)
temporary_link.symlink_to(release)
temporary_link.replace(current)
subprocess.run(["systemctl", "daemon-reload"], check=True)
for context in ("catalog", "orders", "bff"):
    subprocess.run(["systemctl", "enable", f"pedidos360-{context}"], check=True, capture_output=True)
    subprocess.run(["systemctl", "restart", f"pedidos360-{context}"], check=True)

evidence = {"release": release_id, "rdsEndpoint": endpoint, "health": {}, "database": {}}
deadline = time.monotonic() + 180
pending = {"catalog": 8181, "orders": 8182, "bff": 8180}
while pending and time.monotonic() < deadline:
    for context, port in list(pending.items()):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/actuator/health", timeout=2) as result:
                body = json.load(result)
                if result.status == 200 and body["status"] == "UP":
                    evidence["health"][context] = {"status": result.status, "body": body}
                    del pending[context]
        except (OSError, ValueError):
            pass
    if pending:
        time.sleep(2)
if pending:
    raise SystemExit("Services not healthy: " + ", ".join(pending))
for context, other in (("catalog", "orders"), ("orders", "catalog")):
    own_table = "products" if context == "catalog" else "purchase_orders"
    foreign_table = "products" if other == "catalog" else "purchase_orders"
    user = f"pedidos360_{context}_app"
    password = passwords[context + "-app"]
    evidence["database"][context] = {
        "tlsAndMigrations": mysql(user, password, f"SHOW SESSION STATUS LIKE 'Ssl_cipher'; SELECT @@require_secure_transport; SELECT version,description,success FROM pedidos360_{context}.flyway_schema_history; SELECT COUNT(*) AS rows_count FROM pedidos360_{context}.{own_table};"),
        "crossSchemaDenied": mysql(user, password, f"SELECT COUNT(*) FROM pedidos360_{other}.{foreign_table};", expected=1),
        "ddlDenied": mysql(user, password, f"CREATE TABLE pedidos360_{context}.pedidos360_privilege_probe (id INT);", expected=1),
    }
    assert "ERROR 1142" in evidence["database"][context]["crossSchemaDenied"]["stderr"]
    assert "ERROR 1142" in evidence["database"][context]["ddlDenied"]["stderr"]
evidence_file = Path("/var/lib/pedidos360-provision/release-verification.json")
evidence_file.write_text(json.dumps(evidence, indent=2) + "\n")
print(json.dumps(evidence, indent=2))
# Remove only the transferred secret copy after successful installation.
(bundle / "secrets.json").unlink()
