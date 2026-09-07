"""Verify the installed release as root on Pedidos360 EC2, without provisioning again."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.request

if os.geteuid() != 0:
    raise SystemExit('Run on the dedicated EC2 as root')
os.umask(0o077)
current = Path('/opt/pedidos360/current').resolve()
manifest = json.loads((current/'manifest.json').read_text())
report = {'at':dt.datetime.now(dt.timezone.utc).isoformat(),'release':manifest['release'], 'health':{}, 'database':{}, 'artifacts':{}}
for artifact, checksum in manifest['artifacts'].items():
    actual = hashlib.sha256((current/artifact).read_bytes()).hexdigest()
    assert actual == checksum, artifact+' checksum mismatch'
    report['artifacts'][artifact] = actual
pending = {'catalog':8181,'orders':8182,'bff':8180}
deadline = time.monotonic()+150
while pending and time.monotonic()<deadline:
    for context,port in list(pending.items()):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/actuator/health',timeout=2) as response:
                body=json.load(response)
                if response.status==200 and body['status']=='UP':
                    report['health'][context]={'status':response.status,'body':body}
                    del pending[context]
        except (OSError,ValueError):
            pass
    if pending: time.sleep(2)
if pending:
    raise SystemExit('Health timeout: '+','.join(pending))


def mysql(context, sql, expect_failure=False):
    env = dict(line.split('=',1) for line in Path(f'/etc/pedidos360/{context}.env').read_text().splitlines() if '=' in line)
    env = {key: value.strip('"') for key,value in env.items()}
    password = env[context.upper()+'_DB_PASSWORD']
    endpoint = manifest['rdsEndpoint']
    assert re.fullmatch(r'pedidos360-mysql\.[a-z0-9.-]+\.us-east-1\.rds\.amazonaws\.com',endpoint)
    with tempfile.NamedTemporaryFile(mode='w',suffix='.cnf') as config:
        config.write(f'[client]\nhost={endpoint}\nport=3306\nuser={env[context.upper()+"_DB_USER"]}\npassword={password}\nssl-mode=VERIFY_IDENTITY\nssl-ca=/etc/pedidos360/tls/rds-ca-bundle.pem\nconnect-timeout=10\n')
        config.flush()
        result=subprocess.run(['mysql','--defaults-extra-file='+config.name,'--batch','--raw'],input=sql,text=True,capture_output=True,timeout=30)
    safe_error=result.stderr.replace(password,'[REDACTED]')
    if expect_failure:
        assert result.returncode==1 and 'ERROR 1142' in safe_error, 'Expected privilege denial: '+safe_error
    elif result.returncode:
        raise RuntimeError(safe_error)
    return {'exitCode':result.returncode,'stdout':result.stdout,'stderr':safe_error}


for context,other in [('catalog','orders'),('orders','catalog')]:
    own_table='products' if context=='catalog' else 'purchase_orders'
    foreign_table='products' if other=='catalog' else 'purchase_orders'
    report['database'][context]={
        'tlsAndMigrations':mysql(context,f"SHOW SESSION STATUS LIKE 'Ssl_cipher'; SELECT @@version,@@require_secure_transport; SELECT version,description,success FROM pedidos360_{context}.flyway_schema_history; SELECT COUNT(*) AS rows_count FROM pedidos360_{context}.{own_table};"),
        'crossSchemaDenied':mysql(context,f'SELECT COUNT(*) FROM pedidos360_{other}.{foreign_table};',True),
        'ddlDenied':mysql(context,f'CREATE TABLE pedidos360_{context}.pedidos360_privilege_probe (id INT);',True),
    }
    assert 'TLS_' in report['database'][context]['tlsAndMigrations']['stdout']
report['listeners']=subprocess.check_output(['ss','-ltn'],text=True)
for port in (8181,8182):
    assert f'127.0.0.1:{port}' in report['listeners']
    assert f'0.0.0.0:{port}' not in report['listeners']
destination=Path('/var/lib/pedidos360-provision/release-verification.json')
destination.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
# Only this successful release's transferred secret copy; root-only env files remain.
(Path('/home/ubuntu/pedidos360-stage')/manifest['release']/'secrets.json').unlink(missing_ok=True)
