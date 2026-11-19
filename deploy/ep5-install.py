"""EP5 installer for the dedicated Pedidos360 EC2 (root, via SSM). Idempotent; never removes volumes or data.

Usage: python3 ep5-install.py /home/ubuntu/pedidos360-ep5-stage/<release>
Steps: verify SHA-256 manifest -> 2 GiB swap -> Docker -> RDS TLS truststore, schemas and users
(catalog, orders, streams) -> release + env files -> RabbitMQ EP4 cluster -> Kafka cluster, topics and
Kafka UI -> 8 systemd services (heaps of report table 16, staggered start gated by health) -> verification.
Secrets are read from the bundle's private secrets.json, written only to root-only files and never printed.
"""
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import secrets as random
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

assert os.geteuid() == 0 and Path("/var/lib/pedidos360-provision/bootstrap-complete").is_file(), "Run as root after bootstrap"
os.umask(0o077)
bundle = Path(sys.argv[1]).resolve()
assert bundle.is_relative_to("/home/ubuntu/pedidos360-ep5-stage")
manifest = json.loads((bundle / "manifest.json").read_text())
deployment = json.loads((bundle / "deployment.json").read_text())
release_id = manifest["release"]
assert re.fullmatch(r"ep5-\d{8}T\d{6}Z", release_id) and deployment["release"] == release_id
for relative, digest in manifest["files"].items():
    source = (bundle / relative).resolve()
    assert source.is_relative_to(bundle) and hashlib.sha256(source.read_bytes()).hexdigest() == digest, "Checksum mismatch: " + relative
endpoint = deployment["rdsEndpoint"]
assert re.fullmatch(r"pedidos360-mysql\.[a-z0-9.-]+\.us-east-1\.rds\.amazonaws\.com", endpoint), "Unexpected RDS endpoint"
secret_file = bundle / "secrets.json"
passwords = json.loads(secret_file.read_text()) if secret_file.exists() else None
PROVISION = Path("/var/lib/pedidos360-provision")
LOG = Path("/var/log/pedidos360-ep5-install.log")
report = {"release": release_id, "steps": {}}


def run(*command, **kwargs):
    with LOG.open("a") as log:
        log.write("\n$ " + " ".join(map(str, command)) + "\n")
        log.flush()
        return subprocess.run([str(c) for c in command], stdout=log, stderr=subprocess.STDOUT, check=True, **kwargs)


def step(name, value=True):
    report["steps"][name] = value
    print(json.dumps({"step": name, "result": value}), flush=True)


# 1. Swap file of 2 GiB (report 13.1) as margin for memory peaks.
swap = Path("/swapfile")
if not swap.exists():
    run("fallocate", "-l", "2G", swap); swap.chmod(0o600); run("mkswap", swap)
if "/swapfile" not in Path("/proc/swaps").read_text():
    run("swapon", swap)
fstab = Path("/etc/fstab")
if "/swapfile" not in fstab.read_text():
    fstab.write_text(fstab.read_text().rstrip("\n") + "\n/swapfile none swap sw 0 0\n")
Path("/etc/sysctl.d/90-pedidos360.conf").write_text("vm.swappiness=10\n")
run("sysctl", "-p", "/etc/sysctl.d/90-pedidos360.conf")
step("swap", Path("/proc/swaps").read_text().splitlines()[1:])

# 2. Docker Engine + Compose v2 from the Ubuntu archive over HTTPS only (no distribution upgrade).
if not shutil.which("docker"):
    sources = PROVISION / "ep5-apt.sources"
    sources.write_text("Types: deb\nURIs: https://archive.ubuntu.com/ubuntu\nSuites: noble noble-updates noble-backports\n"
                       "Components: main universe restricted multiverse\nSigned-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n\n"
                       "Types: deb\nURIs: https://security.ubuntu.com/ubuntu\nSuites: noble-security\n"
                       "Components: main universe restricted multiverse\nSigned-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n")
    options = ["-o", "Dir::Etc::sourcelist=" + str(sources), "-o", "Dir::Etc::sourceparts=-", "-o", "APT::Get::List-Cleanup=0"]
    env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
    run("apt-get", *options, "update", env=env, timeout=600)
    run("apt-get", *options, "install", "-y", "--no-install-recommends", "docker.io", "docker-compose-v2", env=env, timeout=900)
run("systemctl", "enable", "--now", "docker")
step("docker", subprocess.check_output(["docker", "compose", "version"], text=True).strip())

# 3. RDS: truststore for VERIFY_IDENTITY, then schemas and least-privilege users (idempotent).
tls = Path("/etc/pedidos360/tls")
truststore = tls / "rds-truststore.p12"
if not truststore.exists():
    certificates = re.findall(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", (tls / "rds-ca-bundle.pem").read_text(), re.S)
    assert certificates, "Empty RDS CA bundle"
    for index, certificate in enumerate(certificates):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".crt") as temp:
            temp.write(certificate + "\n"); temp.flush()
            run("/opt/pedidos360/runtime/bin/keytool", "-importcert", "-noprompt", "-alias", f"rds-{index}", "-file", temp.name,
                "-keystore", truststore, "-storetype", "PKCS12", "-storepass", "changeit")
    truststore.chmod(0o644)   # public CA certificates only


def mysql(user, password, sql, expected=0):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".cnf") as config:
        config.write(f"[client]\nhost={endpoint}\nport=3306\nuser={user}\npassword={password}\nssl-mode=VERIFY_IDENTITY\nssl-ca={tls}/rds-ca-bundle.pem\n")
        config.flush()
        result = subprocess.run(["mysql", "--defaults-extra-file=" + config.name, "--batch", "--raw"], input=sql, text=True, capture_output=True)
    if result.returncode != expected:
        raise RuntimeError(f"MySQL {user} exit {result.returncode}: " + re.sub(r"[0-9a-f]{32,48}", "[REDACTED]", result.stderr))
    return {"exitCode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


CONTEXTS = ("catalog", "orders", "streams")
env_dir = Path("/etc/pedidos360")
if passwords is not None:
    for value in passwords.values():
        assert re.fullmatch(r"[0-9a-f]{32,48}", value), "Unexpected secret format"
    statements = []
    for context in CONTEXTS:
        database = "pedidos360_" + context
        statements.append(f"CREATE DATABASE IF NOT EXISTS {database} CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;")
        for role in ("app", "migration"):
            user = f"pedidos360_{context}_{role}"
            statements.append(f"CREATE USER IF NOT EXISTS '{user}'@'%' IDENTIFIED BY '{passwords[context + '-' + role]}' REQUIRE SSL;")
            grants = "SELECT,INSERT,UPDATE,DELETE" + (",CREATE,ALTER,INDEX,DROP,REFERENCES" if role == "migration" else "")
            statements.append(f"GRANT {grants} ON {database}.* TO '{user}'@'%';")
    mysql("pedidos360_master", passwords["master"], "\n".join(statements))
    step("rds-schemas-and-users", [f"pedidos360_{c}" for c in CONTEXTS])
else:
    # Re-run without the private file: reuse the credentials already installed in root-only env files.
    assert all((env_dir / f"{c}.env").exists() for c in ("catalog", "orders", "sales-stream")), "secrets.json required for the first installation"
    step("rds-schemas-and-users", "already provisioned; credentials unchanged")


def env_read(file):
    if not file.exists():
        return {}
    return {k: json.loads(v) if v.startswith('"') else v for line in file.read_text().splitlines() if "=" in line for k, v in [line.split("=", 1)]}


def db_env(context, prefix):
    if passwords is None:   # re-run: keep the installed credentials
        service = "sales-stream" if context == "streams" else context
        return {k: v for k, v in env_read(env_dir / f"{service}.env").items() if k.startswith(prefix + "_")}
    url = (f"jdbc:mysql://{endpoint}:3306/pedidos360_{context}?sslMode=VERIFY_IDENTITY"
           "&trustCertificateKeyStoreUrl=file:///etc/pedidos360/tls/rds-truststore.p12&trustCertificateKeyStoreType=PKCS12"
           "&trustCertificateKeyStorePassword=changeit&fallbackToSystemTrustStore=false&connectionTimeZone=UTC")
    return {f"{prefix}_DB_URL": url, f"{prefix}_DB_USER": f"pedidos360_{context}_app", f"{prefix}_DB_PASSWORD": passwords[context + "-app"],
            f"{prefix}_MIGRATION_USER": f"pedidos360_{context}_migration", f"{prefix}_MIGRATION_PASSWORD": passwords[context + "-migration"]}


# 4. Release directory (0755/0644 so service users can read JARs) and the current symlink.
release = Path("/opt/pedidos360/releases") / release_id
if not release.exists():
    shutil.copytree(bundle, release, ignore=shutil.ignore_patterns("secrets.json"))
for root_dir, dirs, files in os.walk(release):
    Path(root_dir).chmod(0o755)
    for name in files:
        (Path(root_dir) / name).chmod(0o755 if name.endswith(".sh") else 0o644)
for relative, digest in manifest["files"].items():
    assert hashlib.sha256((release / relative).read_bytes()).hexdigest() == digest, "Installed file differs: " + relative
ep4_config, ep5_config = env_dir / "ep4", env_dir / "ep5"
for directory in (ep4_config, ep5_config):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
# Compose project defaults so the report's commands (docker compose -f compose.kafka*.yaml ...) work from the release dir.
(release / ".env").write_text(f"PEDIDOS_EP4_CONFIG_DIR={ep4_config}\nPEDIDOS_EP5_CONFIG_DIR={ep5_config}\n")
(release / ".env").chmod(0o644)   # paths only, no secrets
current = Path("/opt/pedidos360/current")
next_link = Path("/opt/pedidos360/current.next")
next_link.unlink(missing_ok=True); next_link.symlink_to(release); next_link.replace(current)
step("release", str(release))

# 5. RabbitMQ EP4 two-node cluster and topology (contract, queues, exchanges and bindings unchanged).
broker_env = {**os.environ, "PEDIDOS_EP4_CONFIG_DIR": str(ep4_config)}
run("python3", release / "scripts/ep4-broker.py", "up", env=broker_env, timeout=600)
step("rabbitmq", "two nodes up and topology declared")

# 6. Kafka (3 ZooKeeper + 3 brokers), business and DLT topics, Kafka UI with credentials outside Git.
ui_env = ep5_config / "kafka-ui.env"
if not ui_env.exists():
    ui_env.write_text(f"SPRING_SECURITY_USER_NAME=pedidos360-admin\nSPRING_SECURITY_USER_PASSWORD={random.token_hex(24)}\n")
ui_env.chmod(0o600)
kafka_env = {**os.environ, "PEDIDOS_EP5_CONFIG_DIR": str(ep5_config)}

UNIT_HARDENING = "NoNewPrivileges=true\nPrivateTmp=true\n"
compose_units = {
    "pedidos360-rabbit-cluster": ("Pedidos360 EP4 RabbitMQ Compose cluster", "compose.ep4.yaml", "docker.service network-online.target", 300),
    "pedidos360-kafka-cluster": ("Pedidos360 EP5 Kafka cluster (3 ZooKeeper + 3 brokers)", "compose.kafka.yaml", "pedidos360-rabbit-cluster.service", 420),
    "pedidos360-kafka-ui": ("Pedidos360 EP5 Kafka UI", "compose.kafka-ui.yaml", "pedidos360-kafka-cluster.service", 300),
}
for unit, (description, compose, after, timeout) in compose_units.items():
    Path(f"/etc/systemd/system/{unit}.service").write_text(f"""[Unit]
Description={description}
After={after}
Requires=docker.service
[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory={current}
Environment=PEDIDOS_EP4_CONFIG_DIR={ep4_config}
Environment=PEDIDOS_EP5_CONFIG_DIR={ep5_config}
ExecStart=/usr/bin/docker compose -f {current}/{compose} up -d --wait --wait-timeout {timeout - 60}
TimeoutStartSec={timeout}
[Install]
WantedBy=multi-user.target
""")
    Path(f"/etc/systemd/system/{unit}.service").chmod(0o644)
run("systemctl", "daemon-reload")
for unit in ("pedidos360-rabbit-cluster", "pedidos360-kafka-cluster"):
    run("systemctl", "enable", unit); run("systemctl", "restart", unit, timeout=900)
run("bash", release / "scripts/ep5-kafka.sh", "topics", "create", env=kafka_env, timeout=300)
run("systemctl", "enable", "pedidos360-kafka-ui"); run("systemctl", "restart", "pedidos360-kafka-ui", timeout=600)
step("kafka", "cluster healthy, topics created/verified, Kafka UI healthy")

# 7. Eight Spring services. Report table 16 heaps; staggered start: each unit is "started" only once its
# health endpoint answers UP (ExecStartPost), and the next one is ordered After= it.
entra = deployment["entra"]
common = {"SPRING_PROFILES_ACTIVE": "cloud", "JWT_TENANT_ID": entra["tenantId"], "JWT_AUDIENCE": entra["apiClientId"], "JWT_CLIENT_ID": entra["spaClientId"],
          "JWT_ISSUER": f"https://login.microsoftonline.com/{entra['tenantId']}/v2.0",
          "JWT_JWKS_URI": f"https://login.microsoftonline.com/{entra['tenantId']}/discovery/v2.0/keys",
          "SERVER_TOMCAT_ACCESSLOG_ENABLED": "true", "SERVER_TOMCAT_ACCESSLOG_PATTERN": "%t %m %U %s %D", "SERVER_TOMCAT_ACCESSLOG_BUFFERED": "false"}


def rabbit(role):
    return {"PEDIDOS_MESSAGING_ENABLED": "true", "PEDIDOS_MESSAGING_EP4_ENABLED": "true",
            "SPRING_RABBITMQ_ADDRESSES": "127.0.0.1:5675,127.0.0.1:5674" if role == "producer" else "127.0.0.1:5674,127.0.0.1:5675",
            "SPRING_RABBITMQ_DYNAMIC": "false", "RABBIT_VHOST": "pedidos360-ep4", "RABBIT_USER": "pedidos360_ep4_" + role,
            "RABBIT_PASSWORD": (ep4_config / f"rabbit-{role}-password").read_text().strip()}


# name: (artifact, port, heap MiB, extra environment) in staggered start order.
services = {
    "catalog": ("catalog-service", 8181, 256, lambda s: db_env("catalog", "CATALOG")),
    "orders": ("orders-service", 8182, 256, lambda s: {**db_env("orders", "ORDERS"), **rabbit("producer"), "PEDIDOS_KAFKA_ENABLED": "true"}),
    "sales-stream": ("sales-stream-service", 8186, 256, lambda s: db_env("streams", "STREAMS")),
    "bff": ("bff", 8180, 256, lambda s: {"PEDIDOS_SPA_ENABLED": "true", "PEDIDOS_SPA_DIRECTORY": str(current / "frontend")}),
    "receipts": ("receipts-service", 8183, 192, lambda s: {**rabbit("consumer"), "RECEIPTS_DIRECTORY": str(s / "receipts")}),
    "insights": ("order-insights-service", 8185, 192, lambda s: {**rabbit("consumer"), "INSIGHTS_DIRECTORY": str(s / "projections")}),
    "rabbit-admin": ("rabbit-admin-service", 8184, 192, lambda s: {"RABBIT_VHOST": "pedidos360-ep4", "RABBIT_MANAGEMENT_URL": "http://127.0.0.1:15674",
                     "RABBIT_ADMIN_USER": "pedidos360_ep4_admin", "RABBIT_ADMIN_PASSWORD": (ep4_config / "rabbit-admin-password").read_text().strip()}),
    "kafka-admin": ("kafka-admin-service", 8187, 192, lambda s: {}),
}
wait = Path("/usr/local/libexec/pedidos360-wait-health")
wait.parent.mkdir(parents=True, exist_ok=True)
wait.write_text("""#!/bin/sh
# Blocks until 127.0.0.1:$1/actuator/health reports UP (max $2 seconds).
end=$(( $(date +%s) + ${2:-240} ))
while [ "$(date +%s)" -lt "$end" ]; do
  curl -fsS --max-time 2 "http://127.0.0.1:$1/actuator/health" 2>/dev/null | grep -q '"status":"UP"' && exit 0
  sleep 2
done
exit 1
""")
wait.chmod(0o755)
previous_unit = "pedidos360-kafka-ui.service"
for name, (artifact, port, heap, extra) in services.items():
    user = "pedidos360-" + name
    try:
        account = pwd.getpwnam(user)
    except KeyError:
        run("useradd", "--system", "--no-create-home", "--shell", "/usr/sbin/nologin", user)
        account = pwd.getpwnam(user)
    state = Path("/var/lib/pedidos360-" + name); state.mkdir(exist_ok=True, mode=0o750); os.chown(state, account.pw_uid, account.pw_gid)
    logs = Path("/var/log/pedidos360") / name; logs.mkdir(parents=True, exist_ok=True, mode=0o750); os.chown(logs, account.pw_uid, account.pw_gid)
    env = {**common, "SERVER_PORT": str(port), "SERVER_ADDRESS": "0.0.0.0" if name == "bff" else "127.0.0.1",
           "SERVER_TOMCAT_ACCESSLOG_DIRECTORY": str(logs), **extra(state)}
    envfile = env_dir / f"{name}.env"
    envfile.write_text("".join(f"{k}={json.dumps(v)}\n" for k, v in env.items())); envfile.chmod(0o600)
    Path(f"/etc/systemd/system/{user}.service").write_text(f"""[Unit]
Description=Pedidos360 {name} (EP5)
After=network-online.target pedidos360-rabbit-cluster.service pedidos360-kafka-cluster.service {previous_unit}
Wants=network-online.target
StartLimitIntervalSec=600
StartLimitBurst=5
[Service]
Type=exec
User={user}
Group={user}
WorkingDirectory={current}
EnvironmentFile={envfile}
ExecStart=/opt/pedidos360/runtime/bin/java --enable-native-access=ALL-UNNAMED -Djava.net.preferIPv4Stack=true -Xms32m -Xmx{heap}m -XX:MaxMetaspaceSize=128m -Xss512k -jar {current}/{artifact}.jar
ExecStartPost={wait} {port} 240
TimeoutStartSec=300
Restart=on-failure
RestartSec=10
TimeoutStopSec=40
SuccessExitStatus=143
UMask=0027
{UNIT_HARDENING}ProtectSystem=strict
ProtectHome=true
ReadWritePaths={logs} {state}
[Install]
WantedBy=multi-user.target
""")
    Path(f"/etc/systemd/system/{user}.service").chmod(0o644)
    previous_unit = user + ".service"
run("systemctl", "daemon-reload")
for name in services:
    run("systemctl", "enable", "pedidos360-" + name)
    run("systemctl", "restart", "pedidos360-" + name, timeout=330)   # returns only when healthy (staggered)
    step("service-" + name, "UP")

# 8. Verification (no secrets): health, containers, topics, ZooKeeper, memory and listening sockets.
health = {}
for name, (_, port, _, _) in services.items():
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/actuator/health", timeout=5) as response:
        health[name] = json.load(response)["status"]
listeners = subprocess.check_output(["ss", "-H", "-ltn"], text=True).split("\n")
exposed = sorted({line.split()[3] for line in listeners if line.strip() and not re.match(r"(127\.\d+\.\d+\.\d+(%\w+)?|\[::1\]):", line.split()[3])})
report.update(health=health, nonLoopbackListeners=exposed,
              memory=subprocess.check_output(["free", "-m"], text=True), swap=Path("/proc/swaps").read_text(),
              compose={c: subprocess.check_output(["docker", "compose", "-f", str(current / c), "ps", "--format", "{{.Name}} {{.Status}}"],
                                                  env=kafka_env, text=True) for c in ("compose.ep4.yaml", "compose.kafka.yaml", "compose.kafka-ui.yaml")},
              zookeeper=subprocess.check_output(["bash", str(release / "scripts/ep5-kafka.sh"), "zk-status"], env=kafka_env, text=True),
              topics=subprocess.check_output(["bash", str(release / "scripts/ep5-kafka.sh"), "topics", "describe"], env=kafka_env, text=True, stderr=subprocess.DEVNULL),
              units=subprocess.check_output(["systemctl", "is-active", *[f"pedidos360-{n}" for n in services],
                                             *compose_units], text=True).split())
if passwords is not None:
    database = {}
    for context, table in (("catalog", "products"), ("orders", "purchase_orders"), ("streams", "product_sales_daily")):
        user, password = f"pedidos360_{context}_app", passwords[context + "-app"]
        other = "orders" if context != "orders" else "catalog"
        database[context] = {
            "tlsAndMigrations": mysql(user, password, f"SHOW SESSION STATUS LIKE 'Ssl_cipher'; SELECT @@require_secure_transport; "
                                      f"SELECT version,description,success FROM pedidos360_{context}.flyway_schema_history; SELECT COUNT(*) AS rows_count FROM pedidos360_{context}.{table};")["stdout"],
            "crossSchemaDenied": "ERROR 1142" in mysql(user, password, f"SELECT COUNT(*) FROM pedidos360_{other}.flyway_schema_history;", expected=1)["stderr"],
            "ddlDenied": "ERROR 1142" in mysql(user, password, f"CREATE TABLE pedidos360_{context}.pedidos360_privilege_probe (id INT);", expected=1)["stderr"],
        }
    report["database"] = database
(PROVISION / "ep5-install-verification.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report))
assert all(v == "UP" for v in health.values()), "Services unhealthy; inspect journals before retrying"
# Only the BFF (reachable solely from the ALB security group) and sshd (no SG ingress; used through SSM) listen
# beyond loopback. Kafka, ZooKeeper, Kafka UI, RabbitMQ and the other seven services stay on 127.0.0.1.
assert "0.0.0.0:8180" in exposed and set(exposed) <= {"0.0.0.0:8180", "0.0.0.0:22", "[::]:22", "*:22"}, exposed
if secret_file.exists():
    secret_file.unlink()   # remove only the transferred private copy, after a successful installation
