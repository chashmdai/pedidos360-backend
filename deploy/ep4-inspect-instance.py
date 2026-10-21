"""Read-only host inspection. Never emits environment contents or credentials."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request

def command(args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=30)
    return {'code':p.returncode,'out':p.stdout,'error':p.stderr}
report = {'runtime':command(['/opt/pedidos360/runtime/bin/java','--version']),
 'memory':command(['free','-m']), 'disk':command(['df','-h','/']),
 'services':{},'health':{},'artifacts':{},
 'listeners':command(['ss','-ltn']),
 'dockerInstalled':shutil.which('docker') is not None,
 'frontendPresent':Path('/opt/pedidos360/current/frontend/index.html').is_file()}
for service,port in [('catalog',8181),('orders',8182),('bff',8180),('receipts',8183),('rabbit-admin',8184),('insights',8185)]:
    report['services'][service] = command(['systemctl','show','pedidos360-'+service,'--property=LoadState,ActiveState,SubState,MemoryCurrent'])
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/actuator/health',timeout=2) as r:
            report['health'][service] = {'status':r.status,'body':json.load(r)}
    except OSError as exc: report['health'][service] = {'error':str(exc)}
for f in Path('/opt/pedidos360/current').glob('*.jar'):
    report['artifacts'][f.name]=hashlib.sha256(f.read_bytes()).hexdigest()
if report['dockerInstalled']:
    report['dockerVersion']=command(['docker','version','--format','{{.Server.Version}}'])
    report['composeVersion']=command(['docker','compose','version'])
    report['containers']=command(['docker','ps','-a','--format','{{.Names}} {{.Status}}'])
print(json.dumps(report))
