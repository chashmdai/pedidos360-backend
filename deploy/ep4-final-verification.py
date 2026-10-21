"""Read-only final evidence: artifacts, migrations/TLS, data and owned consumers after recovery."""
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import urllib.request

ROOT=Path('/opt/pedidos360/current').resolve()
def environment(context):
    return {k:shlex.split(v)[0] for line in Path('/etc/pedidos360/'+context+'.env').read_text().splitlines() if '=' in line for k,v in [line.split('=',1)]}
def sql(context,query):
    env=environment(context);p=context.upper();host=env[p+'_DB_URL'].split('://',1)[1].split(':',1)[0]
    with tempfile.NamedTemporaryFile(mode='w',suffix='.cnf') as config:
        config.write('[client]\nhost='+host+'\nport=3306\nuser='+env[p+'_DB_USER']+'\npassword='+env[p+'_DB_PASSWORD']+'\nssl-mode=VERIFY_IDENTITY\nssl-ca=/etc/pedidos360/tls/rds-ca-bundle.pem\n');config.flush()
        return subprocess.check_output(['mysql','--defaults-extra-file='+config.name,'--batch','--raw','--skip-column-names','pedidos360_'+context,'-e',query],text=True)
os.environ['PEDIDOS_EP4_CONFIG_DIR']='/etc/pedidos360/ep4'
spec=importlib.util.spec_from_file_location('broker',ROOT/'scripts/ep4-broker.py')
broker=importlib.util.module_from_spec(spec);spec.loader.exec_module(broker)
report={'at':dt.datetime.now(dt.timezone.utc).isoformat(),'environment':'AWS EC2/RDS','release':ROOT.name,
 'artifacts':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob('*.jar')},'health':{},'database':{}}
for name,port in [('bff',8180),('catalog',8181),('orders',8182),('receipts',8183),('rabbit-admin',8184),('insights',8185)]:
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/actuator/health',timeout=5) as response:
        body=json.load(response);assert response.status==200 and body['status']=='UP'
        report['health'][name]={'http':200,'status':body['status']}
    service=subprocess.check_output(['systemctl','is-active','pedidos360-'+name],text=True).strip();assert service=='active'
for context in ('catalog','orders'):
    rows=sql(context,"SHOW SESSION STATUS LIKE 'Ssl_cipher'; SELECT @@require_secure_transport; SELECT version,description,success FROM flyway_schema_history ORDER BY installed_rank; SHOW GRANTS FOR CURRENT_USER;")
    assert 'TLS_AES_' in rows and '\n1\n' in rows
    assert 'CREATE,' not in rows and 'ALTER,' not in rows and 'ALL PRIVILEGES' not in rows
    report['database'][context]={'tlsVerifyIdentitySucceeded':True,'requireSecureTransport':True,'migrationAndGrantOutput':rows}
baseline=json.loads(Path('/var/lib/pedidos360-provision/ep4-data-baseline.json').read_text())
report['preservation']={}
for table,old in baseline.items():
    context,name=table.split('.')
    rows={line.split('\t',1)[0]:hashlib.sha256(line.encode()).hexdigest() for line in sql(context,'SELECT * FROM '+name+' ORDER BY id').splitlines()}
    assert all(rows.get(key)==value for key,value in old.items())
    report['preservation'][table]={'previous':len(old),'now':len(rows),'allPreviousHashesUnchanged':True}
report['queues']=[{k:q.get(k) for k in ('name','node','type','consumers','messages_ready','messages_unacknowledged')} for q in broker.api('GET','queues/'+broker.VHOST)]
assert len(report['queues'])==6
assert all(q['consumers']==1 and q['messages_ready']==0 and q['messages_unacknowledged']==0 for q in report['queues'] if not q['name'].endswith('.failed.v1'))
report['connections']=[{k:c.get(k) for k in ('node','user','vhost','state')} for c in broker.api('GET','connections') if c['vhost']==broker.VHOST]
report['memory']=subprocess.check_output(['free','-m'],text=True)
report['disk']=subprocess.check_output(['df','-h','/'],text=True)
print(json.dumps(report))
