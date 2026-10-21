"""Local development only. Controls exclusively processes recorded by this launcher."""
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from entra_config import environment as entra_environment

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT.parent / "pedidos360-frontend"
STATE = Path.home() / ".local/state/pedidos360-phase1/run"
STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
MANIFEST = STATE / "processes.json"


def fingerprint(pid):
    try:
        base = Path(f"/proc/{pid}")
        # The start time prevents PID reuse from selecting an unrelated process.
        return {"start": base.joinpath("stat").read_text().split(") ", 1)[1].split()[19],
                "command": base.joinpath("cmdline").read_bytes().hex()}
    except (FileNotFoundError, ProcessLookupError):
        return None


def running(record):
    return fingerprint(record["pid"]) == record["fingerprint"]


def records():
    return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}


def stop():
    owned = records()
    for name, record in owned.items():
        if running(record):
            os.killpg(record["pid"], signal.SIGTERM)
            print(f"Stopping Pedidos360 {name}")
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and any(running(r) for r in owned.values()):
        time.sleep(0.2)
    survivors = {n: r for n, r in owned.items() if running(r)}
    MANIFEST.write_text(json.dumps(survivors, indent=2))
    if survivors:
        raise SystemExit("Some Pedidos360 processes are still stopping; inspect their logs.")


def start(mode):
    if mode not in ("entra", "local", "cloud"):
        raise SystemExit("Mode must be entra, local or cloud (frontend only).")
    auth_env = entra_environment(cloud=mode == "cloud") if mode != "local" else {"SPRING_PROFILES_ACTIVE": "local", "VITE_AUTH_MODE": "local"}
    previous = records()
    if any(running(r) for r in previous.values()):
        raise SystemExit("Pedidos360 processes already recorded. Use status or stop before start.")
    java, node = shutil.which("java"), shutil.which("node")
    if not java or not node or java.startswith("/mnt/") or node.startswith("/mnt/"):
        raise SystemExit("Native Linux Java and Node are required.")
    commands = [("identity", 8190, [node, str(ROOT / "scripts/local-identity.mjs"), "serve"], ROOT)] if mode == "local" else []
    for module, port in ([] if mode == "cloud" else [("catalog-service", 8181), ("orders-service", 8182), ("bff", 8180)]):
        jar = ROOT / module / "target" / f"{module}-0.1.0-SNAPSHOT.jar"
        if not jar.exists():
            raise SystemExit("Build the backend with mvn clean verify first.")
        # WSL localhost forwarding recognizes these explicit IPv4 listeners.
        commands.append((module, port, [java, "--enable-native-access=ALL-UNNAMED", "-Djava.net.preferIPv4Stack=true", "-Xms64m", "-Xmx384m", "-jar", str(jar)], ROOT))
    vite = FRONTEND / "node_modules/vite/bin/vite.js"
    if not vite.exists():
        raise SystemExit("Run npm ci in pedidos360-frontend first.")
    commands.append(("frontend", 5173, [node, str(vite), "--host", "127.0.0.1", "--port", "5173", "--strictPort"], FRONTEND))
    for name, port, _, _ in commands:
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                raise SystemExit(f"Port {port} is occupied; no processes were started ({name}).")
    owned = {}
    processes = {}
    try:
        for name, port, command, cwd in commands:
            env = {**os.environ, **auth_env}
            if name == "frontend":
                env.update(VITE_API_BASE_URL=auth_env.get("VITE_API_BASE_URL", "http://127.0.0.1:8180/api/v1"))
            elif name != "identity":
                # Local evidence: method/path/status/duration only, no query strings, headers or tokens.
                env.update(SERVER_TOMCAT_ACCESSLOG_ENABLED="true",
                           SERVER_TOMCAT_ACCESSLOG_DIRECTORY=str(STATE / "http"),
                           SERVER_TOMCAT_ACCESSLOG_PREFIX=f"{name}-access.",
                           SERVER_TOMCAT_ACCESSLOG_PATTERN="%t %m %U %s %D",
                           SERVER_TOMCAT_ACCESSLOG_BUFFERED="false")
            with (STATE / f"{name}.log").open("w") as log:
                process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                           stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            processes[name] = process
            owned[name] = {"pid": process.pid, "fingerprint": fingerprint(process.pid), "port": port}
            MANIFEST.write_text(json.dumps(owned, indent=2))
        deadline = time.monotonic() + 90
        pending = set(owned)
        while pending and time.monotonic() < deadline:
            for name in list(pending):
                record = owned[name]
                # During startup, use the child handle: launchers may still update argv.
                if processes[name].poll() is not None:
                    raise RuntimeError(f"{name} exited; inspect {STATE / (name + '.log')}")
                path = "/" if name == "frontend" else "/health" if name == "identity" else "/actuator/health"
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{record['port']}{path}", timeout=1) as response:
                        if response.status == 200:
                            record["fingerprint"] = fingerprint(record["pid"])
                            MANIFEST.write_text(json.dumps(owned, indent=2))
                            pending.remove(name)
                            print(f"READY Pedidos360 {name}: http://127.0.0.1:{record['port']}", flush=True)
                except (OSError, urllib.error.HTTPError):
                    pass
            if pending:
                time.sleep(0.5)
        if pending:
            raise RuntimeError(f"Health timeout: {sorted(pending)}; logs: {STATE}")
        print(f"Authentication mode: {mode}; logs and owned PID records: {STATE}")
    except BaseException:
        for name, process in processes.items():
            if process.poll() is None:
                owned[name]["fingerprint"] = fingerprint(process.pid)
        MANIFEST.write_text(json.dumps(owned, indent=2))
        stop()
        raise


action = sys.argv[1] if len(sys.argv) > 1 else "status"
if action == "start":
    start(sys.argv[2] if len(sys.argv) > 2 else "entra")
elif action == "stop":
    stop()
elif action == "status":
    for name, record in records().items():
        print(f"{name}: {'RUNNING' if running(record) else 'STOPPED'} (port {record['port']})")
else:
    raise SystemExit("Usage: bash scripts/dev.sh start|status|stop [entra|local|cloud]")
