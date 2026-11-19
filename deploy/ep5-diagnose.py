"""Read-only diagnostics for one Pedidos360 unit: state, recent journal lines (secrets redacted)."""
import json, re, subprocess, sys
unit = sys.argv[1] if len(sys.argv) > 1 else "pedidos360-catalog"
assert re.fullmatch(r"pedidos360-[a-z-]+", unit)
def out(*c):
    r = subprocess.run(list(c), capture_output=True, text=True)
    return re.sub(r"[0-9a-f]{32,64}", "[REDACTED]", (r.stdout + r.stderr))
journal = out("journalctl", "-u", unit, "-n", "80", "--no-pager", "-o", "cat")
print(json.dumps({"status": out("systemctl", "status", unit, "--no-pager", "-l").splitlines()[:14],
                  "journal": [l for l in journal.splitlines() if l.strip()][-45:],
                  "java": out("ls", "-l", "/opt/pedidos360/runtime/bin/java"),
                  "current": out("ls", "-ld", "/opt/pedidos360/current", "/opt/pedidos360/current/"),
                  "envKeys": sorted(re.findall(r"^([A-Z_]+)=", open(f"/etc/pedidos360/{unit.removeprefix('pedidos360-')}.env").read(), re.M))}, indent=1))
