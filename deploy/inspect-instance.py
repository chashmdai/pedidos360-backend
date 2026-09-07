"""Read-only reconciliation on the dedicated EC2; never returns credential contents."""
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

def command(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=15)
    return {"exitCode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}

report = {
    "hostKey": Path('/etc/ssh/ssh_host_ed25519_key.pub').read_text().strip(),
    "bootstrapComplete": Path('/var/lib/pedidos360-provision/bootstrap-complete').exists(),
    "releaseVerification": None,
    "currentRelease": str(Path('/opt/pedidos360/current').resolve()),
    "services": {}, "health": {}, "installedArtifacts": {}, "staging": [],
}
evidence = Path('/var/lib/pedidos360-provision/release-verification.json')
if evidence.exists():
    report['releaseVerification'] = json.loads(evidence.read_text())
redact = []
for directory in Path('/home/ubuntu/pedidos360-stage').glob('*'):
    files = [{"name": p.name, "bytes": p.stat().st_size} for p in directory.iterdir() if p.is_file()]
    report['staging'].append({"release": directory.name, "files": files})
    secret_file = directory / 'secrets.json'
    if secret_file.exists():
        redact.extend(json.loads(secret_file.read_text()).values())
for context, port in [('catalog',8181),('orders',8182),('bff',8180)]:
    env = Path(f'/etc/pedidos360/{context}.env')
    report['services'][context] = {"environmentPresent": env.exists(), "state": command('systemctl','show',f'pedidos360-{context}','--property=LoadState,ActiveState,SubState,Result,ExecMainStatus,ActiveEnterTimestamp')}
    if env.exists():
        for line in env.read_text().splitlines():
            if '_PASSWORD=' in line:
                redact.append(line.split('=',1)[1].strip('"'))
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/actuator/health',timeout=2) as response:
            report['health'][context] = {"status": response.status, "body": json.load(response)}
    except (OSError, ValueError) as exc:
        report['health'][context] = {"error": str(exc)}
    report['services'][context]['recentJournal'] = command('journalctl','--unit=pedidos360-'+context,'--no-pager','--lines=35')
for file in Path('/opt/pedidos360/current').glob('*.jar'):
    report['installedArtifacts'][file.name] = hashlib.sha256(file.read_bytes()).hexdigest()
report['java'] = command('/opt/pedidos360/runtime/bin/java','--version')
report['listeners'] = command('ss','-ltn')
report['installerRunning'] = []
for process in Path('/proc').glob('[0-9]*'):
    try:
        args = (process/'cmdline').read_bytes().split(b'\0')
        if any(arg.endswith(b'/install-release.py') for arg in args):
            report['installerRunning'].append(int(process.name))
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        pass
text = json.dumps(report, indent=2)
for secret in redact:
    text = text.replace(secret, '[REDACTED]')
print(text)
