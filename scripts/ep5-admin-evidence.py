"""E-14 on AWS: kafka-admin-service (127.0.0.1:8187 on the EC2) through an SSM port forward to local 127.0.0.1:18187.
Tokens are read from private files (0600) the user creates outside the repo and are deleted after use; they are never
printed or saved:  ~/.config/pedidos360/aws-<account>/admin-token  (Entra access token, rol Admin + Orders.Read)
                    ~/.config/pedidos360/aws-<account>/user-token   (optional, rol User + Orders.Read)
The only topic created/changed/deleted is pedidos360.lab.demo (lab prefix); business topics are only probed with
operations the service must reject. Output: docs/evidence/ep5/aws/raw-e14.json (rendered by ep5-evidence-report.py).
"""
import datetime as dt
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
import aws_deploy as aws

PORT = 18187
BASE = f"http://127.0.0.1:{PORT}/api/v1/admin/kafka"
LAB, BUSINESS = "pedidos360.lab.demo", "pedidos360.orders.registered.v1"


def token(name):
    path = aws.PRIVATE / name
    if not path.exists():
        return None
    assert path.stat().st_mode & 0o077 == 0, f"{path} must be mode 0600"
    value = path.read_text().strip().removeprefix("Bearer ").strip()
    assert value.count(".") == 2, f"{path} does not look like a JWT"
    return value


def call(method, path, bearer, body=None):
    request = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + bearer} if bearer else {})})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        raw = error.read().decode()
        try:
            return error.code, json.loads(raw) if raw else None
        except ValueError:
            return error.code, raw[:300]


def summary(status, body):
    if isinstance(body, dict) and "partitions" in body and "configs" in body:
        parts = [f"p{p['partition']} leader={p['leader']} replicas={p['replicas']} isr={p['isr']}" for p in body["partitions"]]
        configs = {k: v["value"] if isinstance(v, dict) else v for k, v in body["configs"].items()
                   if k in ("cleanup.policy", "retention.ms", "min.insync.replicas", "segment.ms", "max.message.bytes")}
        return "\n".join(parts + [f"configs: {configs}", f"protectedTopic: {body.get('protectedTopic')}"])
    if isinstance(body, dict) and "groupId" in body:
        return json.dumps(body, ensure_ascii=False, indent=1)
    if isinstance(body, dict) and "title" in body:
        return f"problem: {body.get('status')} {body.get('title')}: {body.get('detail')}"
    return json.dumps(body, ensure_ascii=False)[:1500] if body is not None else "(sin cuerpo)"


identity = aws.call("sts", "get-caller-identity")
assert identity["Account"] == aws.ACCOUNT and "/voclabs/" in identity["Arn"]
admin, user = token("admin-token"), token("user-token")
assert admin, f"Create {aws.PRIVATE / 'admin-token'} (0600) with the Admin access token first"
instance = json.loads(aws.JOURNAL.read_text())["steps"]["ec2"]["response"]["Instances"][0]["InstanceId"]
log = (Path.home() / ".local/state/pedidos360-ep5"); log.mkdir(parents=True, exist_ok=True, mode=0o700)
tunnel = subprocess.Popen([aws.CLI, "ssm", "start-session", "--region", aws.REGION, "--target", instance,
                           "--document-name", "AWS-StartPortForwardingSession",
                           "--parameters", json.dumps({"portNumber": ["8187"], "localPortNumber": [str(PORT)]})],
                          stdin=subprocess.DEVNULL, stdout=(log / "admin-tunnel.log").open("a"), stderr=subprocess.STDOUT,
                          start_new_session=True)
steps = []
try:
    for _ in range(40):
        if tunnel.poll() is not None:
            raise SystemExit("SSM port forward failed: " + (log / "admin-tunnel.log").read_text()[-500:])
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=1):
                break
        except OSError:
            time.sleep(1)
    time.sleep(2)
    plan = [
        ("Clúster (Admin)", "GET", "/cluster", admin, None),
        ("Crear tópico de laboratorio 3x3 (Admin)", "POST", "/topics", admin,
         {"name": LAB, "partitions": 3, "replicationFactor": 3, "configs": {"retention.ms": "3600000"}}),
        ("Consultar tópico (Admin)", "GET", f"/topics/{LAB}", admin, None),
        ("Modificar retention.ms (Admin)", "PATCH", f"/topics/{LAB}/configs", admin, {"configs": {"retention.ms": "7200000"}}),
        ("Aumentar particiones 3 -> 6 (Admin)", "POST", f"/topics/{LAB}/partitions", admin, {"partitions": 6}),
        ("Eliminar tópico de laboratorio (Admin)", "DELETE", f"/topics/{LAB}", admin, None),
        ("Eliminar tópico de negocio (protegido, Admin)", "DELETE", f"/topics/{BUSINESS}", admin, None),
        ("Detalle del grupo agregador (Admin)", "GET", "/consumer-groups/pedidos360-sales-aggregator", admin, None),
        ("Sin token", "GET", "/cluster", None, None),
        ("Bearer inválido", "GET", "/cluster", "invalid.token.value", None),
    ]
    if user:
        plan += [("Token rol User: listar tópicos", "GET", "/topics", user, None),
                 ("Token rol User: eliminar tópico de negocio", "DELETE", f"/topics/{BUSINESS}", user, None)]
    for label, method, path, bearer, body in plan:
        status, response = call(method, path, bearer, body)
        shown_body = f"  body={json.dumps(body)}" if body else ""
        steps.append({"cmd": f"{label}: {method} {path}{shown_body}", "exit": 0, "status": status,
                      "out": f"HTTP {status}\n{summary(status, response)}"})
finally:
    os.killpg(tunnel.pid, signal.SIGTERM)
    for name in ("admin-token", "user-token"):
        (aws.PRIVATE / name).unlink(missing_ok=True)
report = {"at": aws.now(), "instanceId": instance, "commandId": f"SSM port forward 127.0.0.1:{PORT} -> {instance}:8187",
          "status": "Success", "exitCode": 0, "error": "",
          "output": {"action": "e14", "args": ["aws"], "at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "steps": steps}}
aws.save(aws.EVIDENCE / "raw-e14.json", report)
for step in steps:
    print(step["cmd"][:90], "->", step["status"])
print("Tokens deleted; nothing printed or saved.")
