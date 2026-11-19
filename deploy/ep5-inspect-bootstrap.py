"""Read-only bootstrap check on the EP5 EC2: HTTPS-only apt, bootstrap marker, JDK, RDS CA and SSM agent."""
import json, subprocess
from pathlib import Path
p = Path("/var/lib/pedidos360-provision")
def out(*c):
    r = subprocess.run(list(c), capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()
log = (p / "apt-update.log").read_text() if (p / "apt-update.log").exists() else ""
print(json.dumps({
    "cloudInit": out("cloud-init", "status", "--long"),
    "aptHttpsOk": (p / "apt-https-ok").exists(),
    "bootstrapComplete": (p / "bootstrap-complete").exists(),
    "aptSources": Path("/etc/apt/sources.list.d/ubuntu.sources").read_text(),
    "aptUpdateIndexes": [l for l in log.splitlines() if l.startswith(("Hit:", "Get:", "Err:", "W:"))][:12],
    "httpUrisInSources": out("bash", "-c", "grep -rho 'http://[^ ]*' /etc/apt/sources.list.d/ /etc/apt/sources.list 2>/dev/null | sort -u"),
    "java": out("/opt/pedidos360/runtime/bin/java", "--version").splitlines()[:1],
    "rdsCaBundle": Path("/etc/pedidos360/tls/rds-ca-bundle.pem").exists(),
    "ssmAgent": out("snap", "services", "amazon-ssm-agent"),
    "disk": out("df", "-h", "/"), "memory": out("free", "-m"), "os": out("lsb_release", "-ds"),
}, indent=1))
