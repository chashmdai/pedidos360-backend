#!/usr/bin/env python3
"""Pedidos360 · consola de operación (EP5/EP6).

Uso: python3 scripts/p360.py                 menú interactivo
     python3 scripts/p360.py estado          (o status, levantar/up, credenciales/creds, tuneles/tunnels, abrir/open)
     python3 scripts/p360.py demo stream-stop|stream-start|broker-stop|broker-start|describir

Solo biblioteca estándar de Python, la CLI de aws (con session-manager-plugin) y, opcionalmente, wl-copy/wl-paste,
xdg-open y openssl. Reutiliza config/aws-target.json, scripts/aws_deploy.py (llamadas a AWS y destino),
scripts/ssm_remote.py (Run Command) y las acciones revisadas de deploy/ep5-evidence.py en la instancia.
Nunca crea, termina ni borra recursos; todo lo que detiene algo pide confirmación. No imprime secretos.
"""
import argparse
import base64
import configparser
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aws_deploy as aws  # noqa: E402
import ssm_remote  # noqa: E402

RUNNER = aws.ROOT / "deploy/ep5-evidence.py"
API = json.loads((aws.ROOT / "config/aws-public.json").read_text())["apiEndpoint"]
APP_URL = API + "/app/"
RDS_ID = "pedidos360-mysql"
CREDENTIALS = Path(os.environ.get("AWS_SHARED_CREDENTIALS_FILE", Path.home() / ".aws/credentials"))
STATE = Path.home() / ".local/state/pedidos360-ep5"
EXPIRED = ("ExpiredToken", "InvalidClientTokenId", "voc-cancel-cred", "UnrecognizedClientException", "RequestExpired",
           "Unable to locate credentials", "security token included in the request is expired")
SERVICES = ("catalog", "orders", "sales-stream", "bff", "receipts", "insights", "rabbit-admin", "kafka-admin")
GROUPS = ("pedidos360-sales-aggregator", "pedidos360-order-monitor", "pedidos360-sales-dashboard")
TUNNELS = (("Kafka UI", 8090, 18090, "kafka-ui"), ("RabbitMQ Management (nodo 1)", 15674, 25674, "rabbitmq"),
           ("kafka-admin-service (API, requiere JWT Admin)", 8187, 18187, None))
DEMO_STOPPED = set()   # what this session stopped: "sales-stream", "kafka-2"
OK, BAD, WAIT = "✔", "✘", "…"


class CredentialsExpired(Exception):
    pass


class Remote(Exception):
    pass


def safe(text):
    """Never show the lab session name (it embeds the student's e-mail) nor long tokens."""
    text = re.sub(r"assumed-role/voclabs/[^\s\"']+", "assumed-role/voclabs/[sesión]", str(text))
    return re.sub(r"[A-Za-z0-9/+=]{60,}", "[…]", text)


def check_expired(error):
    for marker in EXPIRED:
        if marker in str(error):
            raise CredentialsExpired(marker) from None


def call(service, operation, payload=None):
    try:
        return aws.call(service, operation, payload)
    except RuntimeError as error:
        check_expired(error)
        raise


class Spinner:
    """One-line progress indicator (only on a terminal)."""
    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, text):
        self.text, self.started, self.stop = text, time.time(), threading.Event()
        self.thread = threading.Thread(target=self._spin, daemon=True)

    def _spin(self):
        index = 0
        while not self.stop.wait(0.12):
            sys.stdout.write(f"\r\033[K{self.FRAMES[index % len(self.FRAMES)]} {self.text} ({int(time.time() - self.started)} s)")
            sys.stdout.flush()
            index += 1

    def update(self, text):
        self.text = text

    def __enter__(self):
        if sys.stdout.isatty():
            self.thread.start()
        else:
            print(self.text + " …", flush=True)
        return self

    def __exit__(self, *exc):
        self.stop.set()
        if self.thread.is_alive():
            self.thread.join()
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()


def ask(question, default=False):
    suffix = " [S/n] " if default else " [s/N] "
    try:
        answer = input(question + suffix).strip().lower()
    except EOFError:
        return default
    return default if not answer else answer in ("s", "si", "sí", "y", "yes")


def journal_step(key):
    return json.loads(aws.JOURNAL.read_text())["steps"][key]["response"]


def remote(action, *args, text=None):
    """Run one reviewed action of deploy/ep5-evidence.py on the EC2 and return its steps."""
    try:
        with Spinner(text or f"Ejecutando «{action}» en la instancia por SSM"):
            _, invocation = ssm_remote.run(RUNNER, [action, *args], poll=2)
    except RuntimeError as error:
        check_expired(error)
        raise
    if invocation["Status"] != "Success":
        raise Remote(f"La acción «{action}» falló en la instancia ({invocation['Status']}): "
                     + safe(invocation.get("StandardErrorContent", ""))[-600:])
    return json.loads(invocation["StandardOutputContent"])["steps"]


def identity_ok():
    identity = call("sts", "get-caller-identity")
    if identity["Account"] != aws.ACCOUNT:
        raise SystemExit(f"Las credenciales son de la cuenta {identity['Account']}, no de {aws.ACCOUNT}. Usa la opción 1.")
    return identity


# ---------------------------------------------------------------------------------------------- 1. credenciales
def read_hidden_block():
    print("Pega el bloque [default] de «AWS Details» (AWS CLI) y presiona Enter en una línea vacía.")
    print("(no se muestra en pantalla)")
    lines, fd = [], sys.stdin.fileno()
    old = termios_off(fd)
    try:
        while True:
            line = sys.stdin.readline()
            if not line or (not line.strip() and len(lines) >= 3):
                break
            if line.strip():
                lines.append(line.strip())
            if sum(1 for item in lines if "=" in item) >= 3 and any("session_token" in item for item in lines):
                break
    finally:
        termios_restore(fd, old)
    print(f"Recibidas {len(lines)} líneas.")
    return "\n".join(lines)


def termios_off(fd):
    if not os.isatty(fd):
        return None
    import termios
    old = termios.tcgetattr(fd)
    new = termios.tcgetattr(fd)
    new[3] &= ~termios.ECHO
    termios.tcsetattr(fd, termios.TCSADRAIN, new)
    return old


def termios_restore(fd, old):
    if old is not None:
        import termios
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def parse_block(text):
    values = {}
    for line in text.splitlines():
        match = re.match(r"\s*(aws_access_key_id|aws_secret_access_key|aws_session_token)\s*=\s*(\S+)\s*$", line)
        if match:
            values[match.group(1)] = match.group(2)
    problems = []
    if not re.fullmatch(r"(ASIA|AKIA)[A-Z0-9]{16}", values.get("aws_access_key_id", "")):
        problems.append("aws_access_key_id ausente o con formato inválido")
    if not re.fullmatch(r"[A-Za-z0-9/+=]{40}", values.get("aws_secret_access_key", "")):
        problems.append("aws_secret_access_key ausente o con formato inválido")
    if not re.fullmatch(r"[A-Za-z0-9/+=]{100,}", values.get("aws_session_token", "")):
        problems.append("aws_session_token ausente o con formato inválido")
    return values, problems


def update_credentials():
    text = None
    if shutil.which("wl-paste") and ask("¿Leer el bloque desde el portapapeles (wl-paste)?", default=True):
        text = subprocess.run(["wl-paste", "--no-newline"], capture_output=True, text=True).stdout
        if parse_block(text)[1]:
            print("El portapapeles no contiene un bloque válido; pégalo a mano.")
            text = None
    if text is None:
        text = read_hidden_block()
    values, problems = parse_block(text)
    if problems:
        print("No se actualizaron las credenciales: " + "; ".join(problems) + ".")
        return False
    overriding = [name for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE") if os.environ.get(name)]
    if overriding:
        print("Aviso: estas variables de entorno tienen prioridad sobre el archivo: " + ", ".join(overriding))
    CREDENTIALS.parent.mkdir(mode=0o700, exist_ok=True)
    config = configparser.RawConfigParser()
    if CREDENTIALS.exists():
        backup = CREDENTIALS.with_name(f"credentials.bak-{dt.datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(CREDENTIALS, backup)
        backup.chmod(0o600)
        print(f"Respaldo del archivo anterior: {backup}")
        config.read(CREDENTIALS)
    if not config.has_section("default"):
        config.add_section("default")
    for key, value in values.items():
        config.set("default", key, value)
    previous = os.umask(0o077)
    try:
        temporary = CREDENTIALS.with_suffix(".tmp")
        with open(temporary, "w") as stream:
            config.write(stream)
        temporary.chmod(0o600)
        temporary.replace(CREDENTIALS)
    finally:
        os.umask(previous)
    print(f"Escrito {CREDENTIALS} (0600; otras secciones conservadas). Verificando con STS…")
    try:
        identity = identity_ok()
    except CredentialsExpired as error:
        print(f"{BAD} STS rechazó las credenciales ({error}). Revisa que copiaste el bloque de la sesión actual.")
        return False
    print(f"{OK} Cuenta {identity['Account']} · rol voclabs · sesión válida.")
    return True


# ---------------------------------------------------------------------------------------------- 3. estado
def http_status(url):
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except Exception as error:   # DNS, timeout
        return type(error).__name__


def aws_overview():
    instance = ssm_remote.instance_id()
    item = call("ec2", "describe-instances", {"InstanceIds": [instance]})["Reservations"][0]["Instances"][0]
    ssm = call("ssm", "describe-instance-information", {"Filters": [{"Key": "InstanceIds", "Values": [instance]}]})["InstanceInformationList"]
    rds = call("rds", "describe-db-instances", {"DBInstanceIdentifier": RDS_ID})["DBInstances"][0]["DBInstanceStatus"]
    targets = call("elbv2", "describe-target-health", {"TargetGroupArn": journal_step("target-group")["TargetGroups"][0]["TargetGroupArn"]})
    link = call("apigatewayv2", "get-vpc-link", {"VpcLinkId": journal_step("vpclink")["VpcLinkId"]})["VpcLinkStatus"]
    return {"instance": instance, "ec2": item["State"]["Name"], "ssm": ssm[0]["PingStatus"] if ssm else "sin registro",
            "rds": rds, "target": targets["TargetHealthDescriptions"][0]["TargetHealth"]["State"] if targets["TargetHealthDescriptions"] else "sin target",
            "vpclink": link}


def row(name, value, good):
    mark = OK if good is True else (BAD if good is False else WAIT)
    print(f"  {mark} {name:<38} {value}")


def health(quick=False):
    steps = remote("health", *(["quick"] if quick else []), text="Consultando la instancia por SSM (unidades, servicios, Kafka, RabbitMQ)")
    return steps[0]["json"]


def show_status():
    identity_ok()
    with Spinner("Consultando AWS"):
        overview = aws_overview()
        app, protected = http_status(APP_URL), http_status(API + "/api/v1/ventas/en-vivo")
    print(f"\nPedidos360 · cuenta {aws.ACCOUNT} · {dt.datetime.now():%Y-%m-%d %H:%M:%S}")
    row(f"EC2 {overview['instance']}", overview["ec2"], overview["ec2"] == "running")
    row("SSM", overview["ssm"], overview["ssm"] == "Online")
    row(f"RDS {RDS_ID}", overview["rds"], overview["rds"] == "available")
    row("Target del ALB (BFF :8180)", overview["target"], overview["target"] == "healthy")
    row("VPC Link", overview["vpclink"], overview["vpclink"] == "AVAILABLE")
    row("GET /app/", app, app == 200)
    row("GET /api/v1/ventas/en-vivo sin token", protected, protected == 401)
    if overview["ec2"] != "running" or overview["ssm"] != "Online":
        print("\n  La instancia no está disponible por SSM: usa la opción 2 (Levantar el sistema).")
        return overview, None
    data = health()
    print_health(data)
    return overview, data


def print_health(data):
    units = data["units"]
    active = sum(1 for state in units.values() if state == "active")
    row("Unidades systemd", f"{active}/{len(units)} active" + ("" if active == len(units) else
        " · " + ", ".join(f"{u}={s}" for u, s in units.items() if s != "active")), active == len(units))
    up = sum(1 for state in data["services"].values() if state == "UP")
    row("Servicios (actuator/health)", f"{up}/{len(SERVICES)} UP" + ("" if up == len(SERVICES) else
        " · " + ", ".join(f"{s}={v}" for s, v in data["services"].items() if v != "UP")), up == len(SERVICES))
    modes = data["zookeeper"]
    leaders = [name for name, mode in modes.items() if mode == "leader"]
    row("ZooKeeper", ", ".join(f"{name}={mode}" for name, mode in sorted(modes.items())) or "sin respuesta",
        len(leaders) == 1 and len(modes) == 3)
    containers = data["containers"]
    for label, names in (("Brokers Kafka", ("kafka-1", "kafka-2", "kafka-3")), ("Kafka UI", ("kafka-ui",)),
                         ("RabbitMQ", ("pedidos360-ep4-rabbit-1", "pedidos360-ep4-rabbit-2"))):
        states = {name.replace("pedidos360-ep4-", ""): containers.get(name, "?") for name in names}
        row(label, ", ".join(f"{n}: {s.replace('running ', '')}" for n, s in states.items()),
            all(s == "running healthy" for s in states.values()))
    for group, entry in data.get("groups", {}).items():
        lag = f"lag {entry['lag']}" + (f" (+{entry['unknownLag']} particiones sin offset)" if entry["unknownLag"] else "")
        row("Grupo " + group.removeprefix("pedidos360-"), f"{lag} · {entry['members']} miembros · {entry['partitions']} particiones",
            entry["members"] > 0 and entry["lag"] == 0)
    if data.get("groupsError"):
        print("  " + BAD + " Grupos: " + data["groupsError"])


# ---------------------------------------------------------------------------------------------- 2. levantar
def bring_up(timeout=45 * 60):
    identity_ok()
    instance = ssm_remote.instance_id()
    overview = aws_overview()
    if overview["ec2"] == "stopped":
        print(f"Iniciando EC2 {instance} (mismo ID; no se crea nada)…")
        call("ec2", "start-instances", {"InstanceIds": [instance]})
    elif overview["ec2"] not in ("running", "pending", "stopping"):
        raise SystemExit(f"La EC2 está «{overview['ec2']}»: no se puede iniciar desde aquí.")
    if overview["rds"] == "stopped":
        print(f"Iniciando RDS {RDS_ID} (suele tardar 5–10 min)…")
        call("rds", "start-db-instance", {"DBInstanceIdentifier": RDS_ID})
    started, units_started = time.time(), False
    with Spinner("Esperando") as spinner:
        while True:
            overview = aws_overview()
            if overview["ec2"] == "stopped":   # it was still stopping on the first pass
                call("ec2", "start-instances", {"InstanceIds": [instance]})
            if overview["rds"] == "stopped":
                call("rds", "start-db-instance", {"DBInstanceIdentifier": RDS_ID})
            status = f"EC2 {overview['ec2']} · SSM {overview['ssm']} · RDS {overview['rds']} · target {overview['target']}"
            spinner.update(status)
            if overview["ec2"] == "running" and overview["ssm"] == "Online" and overview["rds"] == "available":
                data = ssm_health_quiet()
                if data:
                    active = sum(1 for s in data["units"].values() if s == "active")
                    up = sum(1 for s in data["services"].values() if s == "UP")
                    spinner.update(f"{status} · unidades {active}/11 · servicios {up}/8 UP")
                    if active == 11 and up == 8 and overview["target"] == "healthy":
                        break
                    failed = [u for u, s in data["units"].items() if s in ("failed", "inactive")]
                    if failed and not units_started and time.time() - started > 120:
                        # RDS may have come up after the services exhausted their restarts: start (never restart) them.
                        spinner.update(f"Iniciando unidades detenidas: {', '.join(failed)}")
                        remote_quiet("start-units")
                        units_started = True
            if time.time() - started > timeout:
                raise SystemExit("Se agotó la espera (45 min). Revisa el estado con la opción 3.")
            time.sleep(15)
    print(f"{OK} Sistema arriba en {int(time.time() - started)} s.")
    show_status()


def ssm_health_quiet():
    try:
        _, invocation = ssm_remote.run(RUNNER, ["health", "quick"], poll=2)
    except RuntimeError as error:
        check_expired(error)
        return None
    if invocation["Status"] != "Success":
        return None
    return json.loads(invocation["StandardOutputContent"])["steps"][0]["json"]


def remote_quiet(action, *args):
    try:
        ssm_remote.run(RUNNER, [action, *args], poll=3)
    except RuntimeError as error:
        check_expired(error)


# ---------------------------------------------------------------------------------------------- 4. túneles
def port_free(port):
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) != 0


def fetch_login(service):
    """Login of a console, encrypted on the EC2 with a one-time RSA key; returns {"user", "password"}."""
    if not shutil.which("openssl"):
        raise Remote("Falta openssl para recibir la credencial cifrada.")
    with tempfile.TemporaryDirectory(prefix="p360-") as directory:
        private, public = Path(directory) / "key.pem", Path(directory) / "pub.pem"
        subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(private)],
                       check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)], check=True, capture_output=True)
        steps = remote("secret", service, base64.b64encode(public.read_bytes()).decode(),
                       text=f"Obteniendo la credencial de {service} (cifrada)")
        cipher = Path(directory) / "secret.bin"
        cipher.write_bytes(base64.b64decode(steps[0]["json"]["ciphertext"]))
        plain = subprocess.run(["openssl", "pkeyutl", "-decrypt", "-inkey", str(private), "-in", str(cipher), "-pkeyopt",
                                "rsa_padding_mode:oaep", "-pkeyopt", "rsa_oaep_md:sha256"], check=True, capture_output=True).stdout
    return json.loads(plain)


def copy(value):
    subprocess.run(["wl-copy"], input=value.encode(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


def clear_clipboard():
    """GNOME keeps the selection after wl-copy exits and ignores `wl-copy --clear`; an empty copy does replace it."""
    subprocess.run(["wl-copy"], input=b"", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    time.sleep(0.3)
    return subprocess.run(["wl-paste", "--no-newline"], capture_output=True).stdout == b""


def offer_login(service, label):
    if not shutil.which("wl-copy"):
        print(f"  (sin wl-copy: la credencial de {label} está en la instancia y se lee en una sesión SSM)")
        return False
    if not ask(f"¿Copiar al portapapeles el usuario y la contraseña de {label}?", default=True):
        return False
    login = fetch_login(service)
    copy(login["user"])
    input(f"  Usuario de {label} copiado. Pégalo y presiona Enter para copiar la contraseña… ")
    copy(login["password"])
    print(f"  Contraseña de {label} copiada (no se muestra). Se borrará del portapapeles al cerrar los túneles.")
    return True


def tunnels():
    identity_ok()
    if not shutil.which("session-manager-plugin"):
        raise SystemExit("Falta session-manager-plugin (requerido por aws ssm start-session).")
    instance = ssm_remote.verify_target()
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    processes, copied = [], False
    try:
        for label, remote_port, local_port, _ in TUNNELS:
            if not port_free(local_port):
                print(f"  {BAD} 127.0.0.1:{local_port} ya está en uso: se omite {label}.")
                continue
            log = (STATE / f"p360-tunnel-{remote_port}.log").open("w")
            process = subprocess.Popen([aws.CLI, "ssm", "start-session", "--region", aws.REGION, "--target", instance,
                                        "--document-name", "AWS-StartPortForwardingSession", "--parameters",
                                        json.dumps({"portNumber": [str(remote_port)], "localPortNumber": [str(local_port)]})],
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            processes.append((label, remote_port, local_port, process))
        with Spinner("Abriendo túneles SSM"):
            deadline = time.time() + 45
            pending = {local for _, _, local, _ in processes}
            while pending and time.time() < deadline:
                for label, remote_port, local_port, process in processes:
                    if process.poll() is not None:
                        output = (STATE / f"p360-tunnel-{remote_port}.log").read_text()
                        check_expired(output)
                        raise Remote(f"El túnel de {label} terminó: " + safe(output)[-300:])
                    if local_port in pending and not port_free(local_port):
                        pending.discard(local_port)
                time.sleep(0.5)
        print("\nTúneles abiertos (solo en 127.0.0.1):")
        for label, remote_port, local_port, _ in processes:
            print(f"  {label:<46} http://127.0.0.1:{local_port}/   (instancia 127.0.0.1:{remote_port})")
        for label, _, local_port, service in TUNNELS:
            if service and any(p[2] == local_port for p in processes):
                copied = offer_login(service, label.split(" (")[0]) or copied
        if not processes:
            print("No se abrió ningún túnel.")
            return
        print("\nCtrl+C para cerrar los túneles.")
        while all(process.poll() is None for *_, process in processes):
            time.sleep(1)
        print("Un túnel se cerró por su cuenta (¿sesión SSM vencida?).")
    except KeyboardInterrupt:
        print()
    finally:
        for *_, process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        cleared = clear_clipboard() if copied else None
        print("Túneles cerrados" + ({True: " y portapapeles limpiado.", False: ". AVISO: no se pudo vaciar el portapapeles; "
              "copia cualquier otro texto para reemplazar la contraseña."}.get(cleared, ".")))


# ---------------------------------------------------------------------------------------------- 5. demo
def outputs(steps):
    return [step for step in steps if step.get("out")]


def show_groups(steps, group):
    """Print one group from the output of the remote «groups» action (describe + members)."""
    no_members = False
    for step in outputs(steps):
        if f"--group {group}" not in step["cmd"]:
            continue
        for line in step["out"].splitlines():
            fields = line.split()
            if "has no active members" in line:
                no_members = True
            elif len(fields) >= 9 and fields[0] == group:
                print(f"  p{fields[2]:<3} offset {fields[3]:<5} log-end {fields[4]:<5} lag {fields[5]:<4} {fields[6][:44]}")
            elif len(fields) == 6 and fields[0] == group:
                print(f"  miembro {fields[1][:44]} · {fields[4]} partición(es) {fields[5]}")
    if no_members:
        print(f"  El grupo {group} no tiene miembros activos.")


def show_topics(steps):
    for step in outputs(steps):
        for line in step["out"].splitlines():
            found = re.search(r"Topic: (\S+)\s+Partition: (\d+)\s+Leader: (\S+)\s+Replicas: (\S+)\s+Isr: (\S+)", line)
            if found:
                topic, partition, leader, replicas, isr = found.groups()
                print(f"  {topic.removeprefix('pedidos360.'):<30} p{partition}  líder {leader:<3} réplicas {replicas:<6} ISR {isr}")
            elif step["cmd"].startswith("docker ") and "kafka-topics" not in step["cmd"] and line.strip():
                print("  " + line)


def demo(choice, sub=None):
    identity_ok()
    if choice == "stream":
        sub = sub or input("  d) detener  i) iniciar: ").strip().lower()[:1]
        if sub == "d":
            if not ask("Esto detiene pedidos360-sales-stream en AWS (la vista en vivo mostrará un error hasta iniciarlo). ¿Continuar?"):
                return
            steps = remote("stop-stream", text="Deteniendo pedidos360-sales-stream")
            DEMO_STOPPED.add("sales-stream")
            print("  sales-stream: " + next((s["out"] for s in steps if "is-active" in s["cmd"]), "?"))
        elif sub == "i":
            steps = remote("start-stream", text="Iniciando pedidos360-sales-stream y esperando UP")
            DEMO_STOPPED.discard("sales-stream")
            print("  sales-stream: " + next((s["out"] for s in steps if "is-active" in s["cmd"]), "?"))
        else:
            return
        print("\n  pedidos360-sales-aggregator")
        show_groups(remote("groups", "pedidos360-sales-aggregator", text="Consultando el grupo agregador"), "pedidos360-sales-aggregator")
    elif choice == "broker":
        sub = sub or input("  d) detener  i) iniciar: ").strip().lower()[:1]
        if sub == "d":
            if not ask("Esto detiene el broker kafka-2 (docker stop; los datos se conservan). ¿Continuar?"):
                return
            steps = remote("stop-broker", text="Deteniendo kafka-2 y esperando la reelección de líderes")
            DEMO_STOPPED.add("kafka-2")
        elif sub == "i":
            steps = remote("start-broker", text="Iniciando kafka-2 y esperando que vuelva al ISR")
            DEMO_STOPPED.discard("kafka-2")
        else:
            return
        show_topics(steps)
    elif choice == "describe":
        show_topics(remote("describe", text="Describiendo los tópicos"))
        steps = remote("groups", text="Describiendo los tres consumer groups")
        for group in GROUPS:
            print(f"\n  {group}")
            show_groups(steps, group)


def offer_restart():
    if not DEMO_STOPPED:
        return
    print(f"\nQuedó detenido por la demo: {', '.join(sorted(DEMO_STOPPED))}.")
    if not ask("¿Iniciarlo ahora?", default=True):
        print("Recuerda iniciarlo con la opción 5 antes de cerrar el laboratorio.")
        return
    if "kafka-2" in DEMO_STOPPED:
        demo("broker", "i")
    if "sales-stream" in DEMO_STOPPED:
        demo("stream", "i")


# ---------------------------------------------------------------------------------------------- 6. abrir
def open_app():
    print(APP_URL)
    if shutil.which("xdg-open"):
        subprocess.Popen(["xdg-open", APP_URL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


# ---------------------------------------------------------------------------------------------- menú y CLI
def guarded(function, *args):
    try:
        if function(*args) is False:
            return 1
    except CredentialsExpired as error:
        print(f"\n{BAD} Las credenciales del laboratorio vencieron o fueron canceladas ({error}).")
        print("  Inicia el laboratorio en AWS Academy, copia «AWS Details» y usa la opción 1 (python3 scripts/p360.py credenciales).")
        return 3
    except (Remote, AssertionError) as error:
        print(f"\n{BAD} {safe(error)}")
        return 1
    except RuntimeError as error:
        print(f"\n{BAD} Error de AWS: {safe(error)[-500:]}")
        return 1
    return 0


def menu():
    options = {"1": ("Actualizar credenciales del lab", update_credentials), "2": ("Levantar el sistema", bring_up),
               "3": ("Estado", show_status), "4": ("Túneles SSM (Kafka UI, RabbitMQ, kafka-admin)", tunnels),
               "5": ("Pasos de la demo", demo_menu), "6": ("Abrir la app en el navegador", open_app)}
    try:
        while True:
            print(f"\nPedidos360 · consola de operación · cuenta {aws.ACCOUNT} ({aws.REGION})")
            for key, (label, _) in options.items():
                print(f"  {key}) {label}")
            print("  0) Salir")
            choice = input("Opción: ").strip()
            if choice == "0":
                break
            if choice in options:
                guarded(options[choice][1])
    except (KeyboardInterrupt, EOFError):
        print()
    guarded(offer_restart)


def demo_menu():
    while True:
        print("\n  Pasos de la demo")
        print("  a) Detener / iniciar pedidos360-sales-stream y ver el lag del agregador")
        print("  b) Detener / iniciar kafka-2 y ver líderes e ISR")
        print("  c) Describir tópicos y consumer groups")
        print("  0) Volver")
        choice = input("  Paso: ").strip().lower()
        if choice == "0" or not choice:
            return
        mapping = {"a": "stream", "b": "broker", "c": "describe"}
        if choice in mapping:
            guarded(demo, mapping[choice])


def main():
    aws.PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)   # aws.call writes request files there
    parser = argparse.ArgumentParser(description="Consola de operación de Pedidos360 (sin argumentos abre el menú).")
    parser.add_argument("command", nargs="?", choices=["credenciales", "creds", "levantar", "up", "estado", "status",
                                                        "tuneles", "tunnels", "demo", "abrir", "open"])
    parser.add_argument("step", nargs="?", choices=["stream-stop", "stream-start", "broker-stop", "broker-start", "describir"])
    args = parser.parse_args()
    if not aws.CLI:
        raise SystemExit("No se encontró la CLI de aws.")
    if args.command is None:
        return menu()
    if args.command == "demo":
        if not args.step:
            parser.error("demo requiere un paso: stream-stop, stream-start, broker-stop, broker-start o describir")
        target = {"stream-stop": ("stream", "d"), "stream-start": ("stream", "i"), "broker-stop": ("broker", "d"),
                  "broker-start": ("broker", "i"), "describir": ("describe", None)}[args.step]
        code = guarded(demo, *target)
        if DEMO_STOPPED:
            print(f"\nAviso: quedó detenido {', '.join(sorted(DEMO_STOPPED))}. Inícialo con «demo "
                  + ("stream-start" if "sales-stream" in DEMO_STOPPED else "broker-start") + "».")
        sys.exit(code)
    function = {"credenciales": update_credentials, "creds": update_credentials, "levantar": bring_up, "up": bring_up,
                "estado": show_status, "status": show_status, "tuneles": tunnels, "tunnels": tunnels,
                "abrir": open_app, "open": open_app}[args.command]
    sys.exit(guarded(function))


if __name__ == "__main__":
    main()
