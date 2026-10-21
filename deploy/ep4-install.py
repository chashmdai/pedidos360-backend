"""Additive EP4 release on the reconciled EC2. Preserve RDS credentials, old release and volumes."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request

assert os.geteuid()==0 and Path('/var/lib/pedidos360-provision/bootstrap-complete').is_file()
os.umask(0o077)
bundle=Path(sys.argv[1]).resolve()
assert bundle.is_relative_to('/home/ubuntu/pedidos360-ep4-stage')
manifest=json.loads((bundle/'manifest.json').read_text())
release_id=manifest['release']
assert release_id.startswith('ep4-') and release_id.replace('-','').isalnum()
for relative,digest in manifest['files'].items():
    source=(bundle/relative).resolve()
    assert source.is_relative_to(bundle) and hashlib.sha256(source.read_bytes()).hexdigest()==digest,'Checksum mismatch: '+relative
release=Path('/opt/pedidos360/releases')/release_id
if release.exists():
    for relative,digest in manifest['files'].items():
        assert hashlib.sha256((release/relative).read_bytes()).hexdigest()==digest,'Existing release differs; inspect before replacing'
else:
    shutil.copytree(bundle,release)
    for root,dirs,files in os.walk(release):
        Path(root).chmod(0o755)
        for name in files:(Path(root)/name).chmod(0o644)
assert shutil.which('docker'),'Run reviewed host preparation first'
backup=Path('/var/lib/pedidos360-provision/ep4-backups')/release_id
backup.mkdir(parents=True,exist_ok=True,mode=0o700)
def env_read(file):
    return {k:shlex.split(v)[0] for line in file.read_text().splitlines() if '=' in line for k,v in [line.split('=',1)]}
original={name:env_read(Path('/etc/pedidos360/'+name+'.env')) for name in ('bff','catalog','orders')}
for name in original:
    for path in (Path('/etc/pedidos360/'+name+'.env'),Path('/etc/systemd/system/pedidos360-'+name+'.service')):
        dest=backup/path.name
        if not dest.exists():shutil.copyfile(path,dest)
config=Path('/etc/pedidos360/ep4');config.mkdir(exist_ok=True,mode=0o700)
broker_env={**os.environ,'PEDIDOS_EP4_CONFIG_DIR':str(config)}
with Path('/var/log/pedidos360-ep4-broker-setup.log').open('a') as log:
    subprocess.run(['python3',str(release/'scripts/ep4-broker.py'),'up'],env=broker_env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=360)
common={k:v for k,v in original['bff'].items() if k.startswith('JWT_')}
contexts={'catalog':('catalog-service',8181,256),'orders':('orders-service',8182,256),'bff':('bff',8180,256),
          'receipts':('receipts-service',8183,128),'rabbit-admin':('rabbit-admin-service',8184,128),'insights':('order-insights-service',8185,128)}
for context,(artifact,port,heap) in contexts.items():
    user='pedidos360-'+context
    try:account=pwd.getpwnam(user)
    except KeyError:
        subprocess.run(['useradd','--system','--no-create-home','--shell','/usr/sbin/nologin',user],check=True)
        account=pwd.getpwnam(user)
    state=Path('/var/lib/pedidos360-'+context);state.mkdir(exist_ok=True,mode=0o750);os.chown(state,account.pw_uid,account.pw_gid)
    logs=Path('/var/log/pedidos360')/context;logs.mkdir(exist_ok=True,mode=0o750);os.chown(logs,account.pw_uid,account.pw_gid)
    env={**original.get(context,{}),**common,'SPRING_PROFILES_ACTIVE':'cloud','SERVER_PORT':str(port),
         'SERVER_ADDRESS':'0.0.0.0' if context=='bff' else '127.0.0.1',
         'SERVER_TOMCAT_ACCESSLOG_ENABLED':'true','SERVER_TOMCAT_ACCESSLOG_PATTERN':'%t %m %U %s %D',
         'SERVER_TOMCAT_ACCESSLOG_BUFFERED':'false','SERVER_TOMCAT_ACCESSLOG_DIRECTORY':str(logs)}
    if context in ('orders','receipts','insights'):
        role='producer' if context=='orders' else 'consumer'
        env.update({'PEDIDOS_MESSAGING_ENABLED':'true','PEDIDOS_MESSAGING_EP4_ENABLED':'true',
          'SPRING_RABBITMQ_ADDRESSES':'127.0.0.1:5675,127.0.0.1:5674' if role=='producer' else '127.0.0.1:5674,127.0.0.1:5675','SPRING_RABBITMQ_DYNAMIC':'false',
          'RABBIT_VHOST':'pedidos360-ep4','RABBIT_USER':'pedidos360_ep4_'+role,
          'RABBIT_PASSWORD':(config/('rabbit-'+role+'-password')).read_text().strip()})
    if context=='receipts':env['RECEIPTS_DIRECTORY']=str(state/'receipts')
    if context=='insights':env['INSIGHTS_DIRECTORY']=str(state/'projections')
    if context=='rabbit-admin':
        env.update({'RABBIT_VHOST':'pedidos360-ep4','RABBIT_MANAGEMENT_URL':'http://127.0.0.1:15674','RABBIT_ADMIN_USER':'pedidos360_ep4_admin',
                    'RABBIT_ADMIN_PASSWORD':(config/'rabbit-admin-password').read_text().strip()})
    if context=='bff':env.update({'PEDIDOS_SPA_ENABLED':'true','PEDIDOS_SPA_DIRECTORY':str(release/'frontend')})
    file=Path('/etc/pedidos360/'+context+'.env')
    file.write_text(''.join(k+'='+json.dumps(v)+'\n' for k,v in env.items()));file.chmod(0o600)
    unit=f'''[Unit]
Description=Pedidos360 {context} EP4
After=network-online.target pedidos360-rabbit-cluster.service
Wants=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=5
[Service]
Type=simple
User={user}
Group={user}
WorkingDirectory=/opt/pedidos360/current
EnvironmentFile=/etc/pedidos360/{context}.env
ExecStart=/opt/pedidos360/runtime/bin/java --enable-native-access=ALL-UNNAMED -Djava.net.preferIPv4Stack=true -Xms32m -Xmx{heap}m -XX:MaxMetaspaceSize=128m -Xss512k -jar /opt/pedidos360/current/{artifact}.jar
Restart=on-failure
RestartSec=10
TimeoutStopSec=40
SuccessExitStatus=143
UMask=0027
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths={logs} {state}
[Install]
WantedBy=multi-user.target
'''
    unitfile=Path('/etc/systemd/system/pedidos360-'+context+'.service');unitfile.write_text(unit);unitfile.chmod(0o644)
cluster_unit=Path('/etc/systemd/system/pedidos360-rabbit-cluster.service')
cluster_unit.write_text(f'''[Unit]
Description=Pedidos360 EP4 RabbitMQ Compose cluster
After=docker.service network-online.target
Requires=docker.service
[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory={release}
Environment=PEDIDOS_EP4_CONFIG_DIR={config}
ExecStart=/usr/bin/docker compose -f {release}/compose.ep4.yaml up -d --wait --wait-timeout 240
TimeoutStartSec=300
[Install]
WantedBy=multi-user.target
''');cluster_unit.chmod(0o644)
current=Path('/opt/pedidos360/current')
previous=backup/'previous-release'
if not previous.exists():previous.write_text(str(current.resolve()))
next_link=Path('/opt/pedidos360/ep4-current.next');next_link.unlink(missing_ok=True);next_link.symlink_to(release);next_link.replace(current)
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','enable','--now','pedidos360-rabbit-cluster'],check=True,capture_output=True)
for context in ('catalog','orders','receipts','insights','rabbit-admin','bff'):
    subprocess.run(['systemctl','enable','pedidos360-'+context],check=True,capture_output=True)
    subprocess.run(['systemctl','restart','pedidos360-'+context],check=True)
pending={k:v[1] for k,v in contexts.items()};health={};deadline=time.monotonic()+200
while pending and time.monotonic()<deadline:
    for name,port in list(pending.items()):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/actuator/health',timeout=3) as response:
                data=json.load(response)
                if response.status==200 and data['status']=='UP':health[name]={'status':200,'body':data};del pending[name]
        except OSError:pass
    if pending:time.sleep(2)
report={'release':release_id,'health':health,'pending':pending,
 'memory':subprocess.check_output(['free','-m'],text=True),
 'compose':subprocess.check_output(['docker','compose','-f',str(release/'compose.ep4.yaml'),'ps','--format','json'],env=broker_env,text=True)}
Path('/var/lib/pedidos360-provision/ep4-install-verification.json').write_text(json.dumps(report))
print(json.dumps(report));assert not pending,'Services unhealthy; inspect exact own journals before retry'
