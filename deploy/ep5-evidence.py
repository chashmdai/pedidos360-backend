"""EP5 evidence runner on the EC2 (run as root through scripts/ep4-ssm.py). Each action runs the report's commands
from /opt/pedidos360/current and prints JSON {action: [{cmd, exit, out}]}. Kafka CLI tools use the approved heap cap
(D-06). Kafka UI is queried through its own API on 127.0.0.1:8090 with the credentials stored on the host; they are
never printed. Output is redacted (hex secrets, bearer tokens). Usage: ep5-evidence.py ACTION [ARG...]
Read-only actions: e01..e06, e08, e19, groups, outbox, logs, topic-tail, rabbit, view.
Actions that change state only as the report's procedure requires: stop-stream/start-stream/restart-stream (E-10, E-15),
invalid (E-11, one invalid record), replay (E-12, republish an already processed record), stop-broker/start-broker (E-13).
"""
import http.cookiejar
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

CURRENT = Path("/opt/pedidos360/current")
CONFIG = Path("/etc/pedidos360")
ORDERS, METRICS, DLT = "pedidos360.orders.registered.v1", "pedidos360.sales.product-metrics.v1", ".DLT"
GROUPS = ("pedidos360-sales-aggregator", "pedidos360-order-monitor", "pedidos360-sales-dashboard")
HEAP = ["-e", "KAFKA_HEAP_OPTS=-Xmx128m", "-e", "KAFKA_OPTS=", "-e", "KAFKA_JMX_OPTS="]
SHOWN_HEAP = '-e KAFKA_HEAP_OPTS="-Xmx128m"'
ENV = dict(os.environ, PEDIDOS_EP4_CONFIG_DIR=str(CONFIG / "ep4"), PEDIDOS_EP5_CONFIG_DIR=str(CONFIG / "ep5"))
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def redact(text):
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{20,}", "Bearer [REDACTED]", text)
    text = re.sub(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+", "[JWT REDACTED]", text)
    return re.sub(r"(?<!sha256:)(?<![0-9a-f-])[0-9a-f]{32,64}(?![0-9a-f-])", "[REDACTED]", text)


def sh(shown, command, stdin=None, timeout=180):
    started = time.time()
    result = subprocess.run(command, cwd=CURRENT, env=ENV, input=stdin, capture_output=True, text=True, errors="replace", timeout=timeout)
    return {"cmd": shown, "exit": result.returncode, "seconds": round(time.time() - started, 1),
            "out": redact((result.stdout + result.stderr).rstrip())}


def kafka(shown_tail, *args, stdin=None, timeout=180):
    return sh(f"docker exec {SHOWN_HEAP} kafka-1 {shown_tail}", ["docker", "exec", *(["-i"] if stdin else []), *HEAP, "kafka-1", *args],
              stdin=stdin, timeout=timeout)


class KafkaUi:
    def __init__(self):
        values = dict(line.split("=", 1) for line in (CONFIG / "ep5/kafka-ui.env").read_text().splitlines() if "=" in line)
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        form = urllib.parse.urlencode({"username": values["SPRING_SECURITY_USER_NAME"],
                                       "password": values["SPRING_SECURITY_USER_PASSWORD"]}).encode()
        self.opener.open("http://127.0.0.1:8090/login", form, timeout=30).read()

    def get(self, path):
        try:
            with self.opener.open("http://127.0.0.1:8090" + path, timeout=60) as response:
                body = response.read().decode()
                return {"cmd": "Kafka UI API GET " + path, "exit": 0, "status": response.status, "json": json.loads(body) if body else None}
        except Exception as exc:   # evidence must show the failure, not hide it
            return {"cmd": "Kafka UI API GET " + path, "exit": 1, "out": redact(str(exc))}


def ui_brokers(ui):
    return [ui.get("/api/clusters"), ui.get("/api/clusters/pedidos360/brokers"), ui.get("/api/clusters/pedidos360/stats")]


def describe(*topics):
    return [kafka(f"kafka-topics --bootstrap-server kafka-1:29092 --describe --topic {t}",
                  "kafka-topics", "--bootstrap-server", "kafka-1:29092", "--describe", "--topic", t) for t in topics]


def groups(*names):
    steps = []
    for g in names or GROUPS:
        steps.append(kafka(f"kafka-consumer-groups --bootstrap-server kafka-1:29092 --describe --group {g}",
                           "kafka-consumer-groups", "--bootstrap-server", "kafka-1:29092", "--describe", "--group", g))
        steps.append(kafka(f"kafka-consumer-groups --bootstrap-server kafka-1:29092 --describe --group {g} --members --verbose",
                           "kafka-consumer-groups", "--bootstrap-server", "kafka-1:29092", "--describe", "--group", g, "--members", "--verbose"))
    return steps


def mysql(context, sql):
    """Read-only queries with the context's application user (TLS VERIFY_IDENTITY); password never printed."""
    service = "sales-stream" if context == "streams" else context
    prefix = {"orders": "ORDERS", "streams": "STREAMS", "catalog": "CATALOG"}[context]
    values = {k: v for line in (CONFIG / f"{service}.env").read_text().splitlines() if "=" in line for k, v in [line.split("=", 1)]}
    host = re.search(r"jdbc:mysql://([^:/]+)", values[f"{prefix}_DB_URL"]).group(1)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".cnf") as cnf:
        cnf.write(f"[client]\nhost={host}\nport=3306\nuser={values[prefix + '_DB_USER']}\npassword={values[prefix + '_DB_PASSWORD'].strip(chr(34))}\n"
                  f"ssl-mode=VERIFY_IDENTITY\nssl-ca={CONFIG}/tls/rds-ca-bundle.pem\ndatabase=pedidos360_{context}\n")
        cnf.flush()
        step = sh(f"mysql (pedidos360_{context}_app, TLS VERIFY_IDENTITY) -e \"{sql}\"",
                  ["mysql", "--defaults-extra-file=" + cnf.name, "--batch", "--table", "-e", sql])
    return step


def journal(unit, pattern, since="-30min", lines=40):
    step = sh(f"journalctl -u {unit} --since {since} -o cat | grep -E '{pattern}' | tail -{lines}",
              ["bash", "-c", f"journalctl -u {unit} --since {since} --no-pager -o cat | grep -E '{pattern}' | tail -{lines}"])
    return step


def tail(topic, count=5, key=None, headers=True):
    """Last COUNT records of every partition (bounded, no consumer group: --partition/--offset leave no group)."""
    steps = []
    for partition in (0, 1, 2):
        props = ["--property", "print.key=true", "--property", "print.partition=true", "--property", "print.offset=true",
                 "--property", "print.timestamp=true"] + (["--property", "print.headers=true"] if headers else [])
        args = ["kafka-console-consumer", "--bootstrap-server", "kafka-1:29092", "--topic", topic, "--partition", str(partition),
                "--offset", "earliest", "--timeout-ms", "8000", *props]
        step = kafka(f"kafka-console-consumer --bootstrap-server kafka-1:29092 --topic {topic} --partition {partition} "
                     f"--offset earliest --timeout-ms 8000 --property print.key=true ... ", *args, timeout=120)
        lines = [l for l in step["out"].splitlines() if not l.startswith(("Processed a total", "[")) and "TimeoutException" not in l]
        if key:
            lines = [l for l in lines if key in l]
        step["out"] = "\n".join(lines[-count:]) + f"\n({len(lines)} matching records in partition {partition}; last {count} shown)"
        steps.append(step)
    return steps


def units():
    return [sh("systemctl is-active pedidos360-sales-stream", ["systemctl", "is-active", "pedidos360-sales-stream"]),
            sh("curl -s http://127.0.0.1:8186/actuator/health", ["curl", "-s", "--max-time", "5", "http://127.0.0.1:8186/actuator/health"])]


def wait_health(port, seconds=300):
    deadline = time.time() + seconds
    while time.time() < deadline:
        result = subprocess.run(["curl", "-s", "--max-time", "3", f"http://127.0.0.1:{port}/actuator/health"], capture_output=True, text=True)
        if '"UP"' in result.stdout:
            return {"cmd": f"wait for 127.0.0.1:{port}/actuator/health UP", "exit": 0, "out": result.stdout}
        time.sleep(3)
    return {"cmd": f"wait for 127.0.0.1:{port}/actuator/health UP", "exit": 1, "out": "timeout"}


def memory_by_unit():
    lines = []
    for unit in ("catalog", "orders", "sales-stream", "bff", "receipts", "insights", "rabbit-admin", "kafka-admin"):
        values = dict(line.split("=", 1) for line in subprocess.run(
            ["systemctl", "show", f"pedidos360-{unit}", "-p", "MemoryCurrent", "-p", "MemoryPeak", "-p", "MemoryMax"],
            capture_output=True, text=True).stdout.split())
        mib = lambda v: f"{int(v) // 1048576} MiB" if v.isdigit() else v
        lines.append(f"pedidos360-{unit:<14} current={mib(values.get('MemoryCurrent', '?')):>8}  peak={mib(values.get('MemoryPeak', '?')):>8}")
    return {"cmd": "systemctl show pedidos360-<servicio> -p MemoryCurrent -p MemoryPeak", "exit": 0, "out": "\n".join(lines)}


action, args = sys.argv[1], sys.argv[2:]
steps = []
if action == "e01":
    steps += [sh("docker compose -f compose.kafka.yaml up -d --wait", ["docker", "compose", "-f", "compose.kafka.yaml", "up", "-d", "--wait", "--wait-timeout", "300"], timeout=400),
              sh("docker compose -f compose.kafka.yaml ps", ["docker", "compose", "-f", "compose.kafka.yaml", "ps", "--format",
                 "table {{.Name}}\t{{.Image}}\t{{.State}}\t{{.Status}}\t{{.Ports}}"])]
elif action == "e02":
    steps.append(sh("bash scripts/ep5-kafka.sh zk-status", ["bash", "scripts/ep5-kafka.sh", "zk-status"]))
elif action == "e03":
    steps.append(sh(f"docker exec {SHOWN_HEAP} kafka-1 zookeeper-shell zookeeper-1:2181 ls /brokers/ids",
                    ["docker", "exec", *HEAP, "kafka-1", "zookeeper-shell", "zookeeper-1:2181", "ls", "/brokers/ids"]))
    steps.append(sh(f"docker exec {SHOWN_HEAP} kafka-1 zookeeper-shell zookeeper-1:2181 get /controller",
                    ["docker", "exec", *HEAP, "kafka-1", "zookeeper-shell", "zookeeper-1:2181", "get", "/controller"]))
    steps += ui_brokers(KafkaUi())
elif action == "e04":
    steps += [sh("docker compose -f compose.kafka-ui.yaml up -d --wait", ["docker", "compose", "-f", "compose.kafka-ui.yaml", "up", "-d", "--wait", "--wait-timeout", "180"], timeout=300),
              sh("docker compose -f compose.kafka-ui.yaml ps", ["docker", "compose", "-f", "compose.kafka-ui.yaml", "ps", "--format",
                 "table {{.Name}}\t{{.Image}}\t{{.State}}\t{{.Status}}\t{{.Ports}}"])]
    ui = KafkaUi()
    steps += [{"cmd": "Kafka UI login (LOGIN_FORM, credentials from /etc/pedidos360/ep5/kafka-ui.env, not printed)", "exit": 0, "out": "session established"},
              ui.get("/api/clusters"), ui.get("/api/clusters/pedidos360/topics?perPage=50&showInternal=false")]
elif action == "e05":
    steps += describe(ORDERS, METRICS)
    ui = KafkaUi()
    steps += [ui.get(f"/api/clusters/pedidos360/topics/{t}") for t in (ORDERS, METRICS)]
elif action == "e06":
    for t in (ORDERS, METRICS, ORDERS + DLT, METRICS + DLT):
        steps.append(kafka(f"kafka-configs --bootstrap-server kafka-1:29092 --entity-type topics --entity-name {t} --describe",
                           "kafka-configs", "--bootstrap-server", "kafka-1:29092", "--entity-type", "topics", "--entity-name", t, "--describe"))
elif action in ("e08", "groups"):
    steps += groups(*args)
    if action == "e08":
        ui = KafkaUi()
        steps += [ui.get(f"/api/clusters/pedidos360/consumer-groups/{g}") for g in GROUPS]
elif action == "e19":
    steps += [sh("free -m", ["free", "-m"]), sh("swapon --show", ["swapon", "--show"]),
              sh("docker stats --no-stream", ["docker", "stats", "--no-stream", "--format",
                 "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"]),
              sh("docker inspect (mem_limit)", ["bash", "-c", "docker inspect --format '{{.Name}} mem_limit={{.HostConfig.Memory}}' $(docker ps -q)"]),
              sh("systemctl status pedidos360-* --no-pager", ["bash", "-c", "systemctl status 'pedidos360-*' --no-pager -n 0 | grep -E '^(●|○|×)|Active:|Memory:|Main PID:'"]),
              memory_by_unit()]
elif action == "outbox":   # E-07: order_stream_outbox by orderId (optional) or latest
    where = f"WHERE order_id='{args[0]}'" if args and re.fullmatch(UUID, args[0]) else ""
    steps.append(mysql("orders", f"SELECT event_id, order_id, created_at, published_at, attempts, last_error_code FROM order_stream_outbox {where} ORDER BY created_at DESC LIMIT 10"))
elif action == "sql":   # read-only, fixed allowlist of statements
    queries = {
        "outbox-columns": ("orders", "SHOW COLUMNS FROM order_stream_outbox"),
        "outbox": ("orders", "SELECT event_id, order_id, created_at, published_at, attempts, last_error_code FROM order_stream_outbox ORDER BY created_at DESC LIMIT 10"),
        "rabbit-outbox": ("orders", "SELECT event_id, order_id, created_at, published_at, attempts, last_error_code FROM order_event_outbox ORDER BY created_at DESC LIMIT 10"),
        # Never select owner_subject (Entra oid of the user).
        "orders": ("orders", "SELECT o.id, o.status, o.created_at, i.product_name, i.quantity, i.unit_price, i.currency "
                             "FROM purchase_orders o JOIN order_items i ON i.order_id = o.id ORDER BY o.created_at DESC, i.id LIMIT 30"),
        "products": ("catalog", "SELECT id, name, price, currency, stock FROM products"),
        "streams-tables": ("streams", "SHOW TABLES"),
        "sales": ("streams", "SELECT * FROM product_sales_daily ORDER BY 1"),
        "processed": ("streams", "SELECT COUNT(*) AS processed_events FROM processed_stream_event"),
    }
    for name in args:
        context, sql = queries[name]
        steps.append(mysql(context, sql))
elif action == "logs":   # logs UNIT PATTERN [SINCE]
    assert re.fullmatch(r"pedidos360-[a-z-]+", args[0]) and re.fullmatch(r"[A-Za-z0-9_|.: -]+", args[1])
    steps.append(journal(args[0], args[1], *(args[2:3] or ["-30min"])))
elif action == "topic-tail":   # topic-tail TOPIC [COUNT] [KEY]
    assert args[0] in (ORDERS, METRICS, ORDERS + DLT, METRICS + DLT)
    steps += tail(args[0], int(args[1]) if len(args) > 1 else 5, args[2] if len(args) > 2 else None)
elif action == "dlt":   # E-11: DLT records with Spring's headers decoded (partition int32, offset/timestamp int64 big-endian)
    import struct
    topic = ORDERS + DLT
    numeric = {"kafka_dlt-original-partition": ">i", "kafka_dlt-original-offset": ">q", "kafka_dlt-original-timestamp": ">q"}
    strings = ("kafka_dlt-original-topic", "kafka_dlt-original-consumer-group", "kafka_dlt-exception-fqcn",
               "kafka_dlt-exception-cause-fqcn", "kafka_dlt-exception-message", "kafka_dlt-exception-stacktrace")
    for partition in (0, 1, 2):
        raw = subprocess.run(["docker", "exec", *HEAP, "kafka-1", "kafka-console-consumer", "--bootstrap-server", "kafka-1:29092",
                              "--topic", topic, "--partition", str(partition), "--offset", "earliest", "--timeout-ms", "8000",
                              "--property", "print.key=true", "--property", "print.partition=true", "--property", "print.offset=true",
                              "--property", "print.headers=true"], capture_output=True, timeout=120).stdout
        records = [b"CreateTime:" + r for r in raw.split(b"CreateTime:")[1:]] or [r for r in raw.split(b"Partition:")[1:]]
        lines = []
        for record in raw.split(b"Partition:")[1:]:
            fields = {"dltPartition": partition, "dltOffset": int(record.split(b"Offset:", 1)[1].split(b"\t", 1)[0])}
            for name, fmt in numeric.items():
                at = record.find(name.encode() + b":")
                if at >= 0:
                    start = at + len(name) + 1
                    fields[name] = struct.unpack(fmt, record[start:start + struct.calcsize(fmt)])[0]
            for name in strings:
                at = record.find(name.encode() + b":")
                if at >= 0:
                    rest = record[at + len(name) + 1:]
                    end = min([i for i in (rest.find(b",kafka_dlt-"), rest.find(b"\n"), rest.find(b"\t")) if i >= 0] or [len(rest)])
                    fields[name] = rest[:min(end, 300)].decode("utf-8", "replace")
            tail_part = record.rsplit(b"\t", 2)
            fields["key"], fields["value"] = tail_part[-2].decode("utf-8", "replace"), tail_part[-1].strip().decode("utf-8", "replace")[:300]
            lines.append(json.dumps(fields, ensure_ascii=False))
        steps.append({"cmd": f"docker exec {SHOWN_HEAP} kafka-1 kafka-console-consumer --bootstrap-server kafka-1:29092 --topic {topic} "
                             f"--partition {partition} --offset earliest --property print.headers=true ... (encabezados kafka_dlt-* decodificados)",
                      "exit": 0, "out": redact("\n".join(lines) or "(sin registros)")})
elif action == "describe":
    steps += describe(ORDERS, METRICS, ORDERS + DLT, METRICS + DLT)
elif action == "stop-stream":    # E-10
    steps += [sh("systemctl stop pedidos360-sales-stream", ["systemctl", "stop", "pedidos360-sales-stream"], timeout=120), *units()]
elif action in ("start-stream", "restart-stream"):   # E-10 / E-15
    verb = action.split("-")[0]
    steps += [sh(f"systemctl {verb} pedidos360-sales-stream", ["systemctl", verb, "pedidos360-sales-stream"], timeout=400),
              wait_health(8186), *units()]
elif action == "invalid":   # E-11: one record with a key and invalid JSON (no business data)
    key = "e11-invalid-" + time.strftime("%H%M%S")
    steps.append(kafka(f"kafka-console-producer --bootstrap-server kafka-1:29092 --topic {ORDERS} --property parse.key=true "
                       f"--property key.separator=\"|\"   <<< '{key}|{{\"eventId\": no-es-json'",
                       "kafka-console-producer", "--bootstrap-server", "kafka-1:29092", "--topic", ORDERS,
                       "--property", "parse.key=true", "--property", "key.separator=|", stdin=key + '|{"eventId": no-es-json\n'))
    steps.append({"cmd": "key", "exit": 0, "out": key})
elif action == "replay":   # E-12: republish the exact payload and key of an already processed record (latest of partition P)
    partition, offset = int(args[0]), int(args[1])
    read = kafka(f"kafka-console-consumer --bootstrap-server kafka-1:29092 --topic {ORDERS} --partition {partition} --offset {offset} "
                 "--max-messages 1 --property print.key=true --property key.separator=\"|\"",
                 "kafka-console-consumer", "--bootstrap-server", "kafka-1:29092", "--topic", ORDERS, "--partition", str(partition),
                 "--offset", str(offset), "--max-messages", "1", "--timeout-ms", "15000",
                 "--property", "print.key=true", "--property", "key.separator=|")
    record = next(l for l in read["out"].splitlines() if "|" in l and l.split("|", 1)[1].startswith("{"))
    key, payload = record.split("|", 1)
    assert re.fullmatch(UUID, key) and json.loads(payload)["eventId"]
    steps.append(dict(read, out=record))
    steps.append(kafka(f"kafka-console-producer --bootstrap-server kafka-1:29092 --topic {ORDERS} --property parse.key=true "
                       "--property key.separator=\"|\"   <<< (mismo registro: misma clave y mismo payload)",
                       "kafka-console-producer", "--bootstrap-server", "kafka-1:29092", "--topic", ORDERS,
                       "--property", "parse.key=true", "--property", "key.separator=|", stdin=record + "\n"))
    steps.append({"cmd": "eventId republicado", "exit": 0, "out": json.loads(payload)["eventId"]})
elif action == "stop-broker":   # E-13
    steps += [sh("docker stop kafka-2", ["docker", "stop", "kafka-2"], timeout=120)]
    time.sleep(15)
    steps += describe(ORDERS, METRICS)
elif action == "start-broker":
    steps += [sh("docker start kafka-2", ["docker", "start", "kafka-2"], timeout=120)]
    for _ in range(60):
        out = subprocess.run(["docker", "inspect", "--format", "{{.State.Health.Status}}", "kafka-2"], capture_output=True, text=True).stdout.strip()
        if out == "healthy":
            break
        time.sleep(5)
    time.sleep(20)   # leave time for the replicas to catch up and rejoin the ISR
    steps += [sh("docker inspect kafka-2 (health)", ["docker", "inspect", "--format", "{{.State.Health.Status}}", "kafka-2"]), *describe(ORDERS, METRICS)]
elif action == "rabbit":   # E-16: cluster, queues with DLQ and exchanges (read-only rabbitmqctl)
    for shown, command in (("cluster_status", ["cluster_status"]),
                           ("list_queues name type messages_ready messages_unacknowledged consumers",
                            ["list_queues", "name", "type", "messages_ready", "messages_unacknowledged", "consumers"]),
                           ("list_exchanges name type", ["list_exchanges", "name", "type"]),
                           ("list_bindings source_name destination_name routing_key", ["list_bindings", "source_name", "destination_name", "routing_key"])):
        configured = re.search(r"^RABBIT_VHOST=(.*)$", (CONFIG / "orders.env").read_text(), re.M).group(1).strip('"')
        vhost = [] if command == ["cluster_status"] else ["-p", configured]   # vhost the services use (EP4: pedidos360-ep4)
        steps.append(sh(f"docker exec pedidos360-ep4-rabbit-1 rabbitmqctl -q {' '.join(vhost)} {shown}".replace("  ", " "),
                        ["docker", "exec", "pedidos360-ep4-rabbit-1", "rabbitmqctl", "-q", *vhost, *command]))
else:
    raise SystemExit("Unknown action " + action)
print(json.dumps({"action": action, "args": args, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "steps": steps}, ensure_ascii=False))
