"""Dedicated EC2 only: read-only data baseline, then install Docker if absent. No distro upgrade."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

assert os.geteuid()==0 and Path('/var/lib/pedidos360-provision/bootstrap-complete').is_file()
os.umask(0o077)
def environment(context):
    return {k:shlex.split(v)[0] for line in Path('/etc/pedidos360/'+context+'.env').read_text().splitlines() if '=' in line for k,v in [line.split('=',1)]}
def rows(context,table):
    env=environment(context);prefix=context.upper()
    host=env[prefix+'_DB_URL'].split('://',1)[1].split(':',1)[0]
    database='pedidos360_'+context
    with tempfile.NamedTemporaryFile(mode='w',suffix='.cnf') as config:
        config.write('[client]\nhost='+host+'\nport=3306\nuser='+env[prefix+'_DB_USER']+'\npassword='+env[prefix+'_DB_PASSWORD']+'\nssl-mode=VERIFY_IDENTITY\nssl-ca=/etc/pedidos360/tls/rds-ca-bundle.pem\n')
        config.flush()
        command=['mysql','--defaults-extra-file='+config.name,'--batch','--raw','--skip-column-names',database,'-e','SELECT * FROM '+table+' ORDER BY id']
        result=subprocess.run(command,capture_output=True,check=True)
    return {line.split(b'\t',1)[0].decode():hashlib.sha256(line).hexdigest() for line in result.stdout.splitlines()}
baseline={context+'.'+table:rows(context,table) for context,table in [('catalog','products'),('orders','purchase_orders'),('orders','order_items')]}
file=Path('/var/lib/pedidos360-provision/ep4-data-baseline.json')
if not file.exists():file.write_text(json.dumps(baseline))
else:
    old=json.loads(file.read_text())
    assert all(baseline[table].get(key)==value for table,rows in old.items() for key,value in rows.items()),'Previously recorded data changed; inspect before continuing'
if not shutil.which('docker'):
    sources=Path('/var/lib/pedidos360-provision/ep4-apt.sources')
    sources.write_text('Types: deb\nURIs: https://archive.ubuntu.com/ubuntu\nSuites: noble noble-updates noble-backports\nComponents: main universe restricted multiverse\nSigned-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n\nTypes: deb\nURIs: https://security.ubuntu.com/ubuntu\nSuites: noble-security\nComponents: main universe restricted multiverse\nSigned-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n')
    options=['-o','Dir::Etc::sourcelist='+str(sources),'-o','Dir::Etc::sourceparts=-','-o','APT::Get::List-Cleanup=0']
    # Logs stay on the host; publish only status/version, not unbounded package output.
    with Path('/var/log/pedidos360-ep4-docker-install.log').open('a') as log:
        for operation in [['update'],['install','-y','--no-install-recommends','docker.io','docker-compose-v2']]:
            subprocess.run(['apt-get',*options,*operation],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=500,
                env={**os.environ,'DEBIAN_FRONTEND':'noninteractive'})
    subprocess.run(['systemctl','enable','--now','docker'],check=True,capture_output=True)
report={'baselineCounts':{key:len(value) for key,value in baseline.items()},'baselineSha256':hashlib.sha256(file.read_bytes()).hexdigest(),
 'docker':subprocess.check_output(['docker','version','--format','{{.Server.Version}}'],text=True).strip(),
 'compose':subprocess.check_output(['docker','compose','version'],text=True).strip(),
 'disk':subprocess.check_output(['df','-h','/'],text=True)}
print(json.dumps(report))
