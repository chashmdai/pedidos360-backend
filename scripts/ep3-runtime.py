"""WSL codex runtime, exclusively owned EP3 processes; existing MySQL secrets are reused, never rotated."""
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from entra_config import environment as entra_environment

ROOT=Path(__file__).resolve().parent.parent
CONFIG=Path(os.environ.get('PEDIDOS_EP3_CONFIG_DIR',Path.home()/'.config/pedidos360/ep3'))
STATE=Path.home()/'.local/state/pedidos360-ep3'
PORTS={'catalog-service':19181,'orders-service':19182,'bff':19180,'receipts-service':19183,'rabbit-admin-service':19184,'frontend':5173,'identity':8190}
for directory in (CONFIG,STATE): directory.mkdir(parents=True,exist_ok=True,mode=0o700)
MANIFEST=STATE/'processes.json'


def docker(*args):
    return subprocess.check_output(['docker',*args],text=True).strip()


def secret(name):
    file=CONFIG/(name+'-password')
    if not file.exists():
        file.write_text(secrets.token_hex(24)+'\n');file.chmod(0o600)
    return file.read_text().strip()


def setup():
    if os.getuid()==0 or os.environ.get('USER')!='codex':
        raise SystemExit('Use WSL user codex; no root or Windows build')
    metadata=json.loads(docker('inspect','pedidos360-mysql'))[0]
    if metadata['Config']['Labels'].get('Project')!='Pedidos360':
        raise SystemExit('Existing MySQL identity not recognized; no changes made')
    components={name:{} for name in PORTS}
    # Read only the four existing application/migrator secrets from this project's container.
    for context in ('catalog','orders'):
        prefix=context.upper();environment=components[context+'-service']
        environment[prefix+'_DB_URL']=f'jdbc:mysql://127.0.0.1:13306/pedidos360_{context}?sslMode=DISABLED&allowPublicKeyRetrieval=true&connectionTimeZone=UTC'
        for role in ('app','migration'):
            password=docker('exec','pedidos360-mysql','cat','/run/secrets/'+context+'_'+role)
            key='DB' if role=='app' else 'MIGRATION'
            environment[f'{prefix}_{key}_USER']=f'pedidos360_{context}_{role}'
            environment[f'{prefix}_{key}_PASSWORD']=password
    for component,role in (('orders-service','producer'),('receipts-service','consumer')):
        components[component].update(RABBIT_USER='pedidos360_ep3_'+role,RABBIT_PASSWORD=secret('rabbit-'+role))
    secret('rabbit-admin')
    components['rabbit-admin-service'].update(RABBIT_ADMIN_USER='pedidos360_ep3_admin',RABBIT_ADMIN_PASSWORD=secret('rabbit-admin'))
    components['receipts-service']['RECEIPTS_DIRECTORY']=str(STATE/'receipts')
    components['orders-service']['CATALOG_URL']='http://127.0.0.1:19181'
    components['bff'].update(CATALOG_URL='http://127.0.0.1:19181',ORDERS_URL='http://127.0.0.1:19182')
    file=CONFIG/'components.json';file.write_text(json.dumps(components));file.chmod(0o600)
    (CONFIG/'rabbit-admin-password').chmod(0o444) # enclosing directory 0700; container entrypoint reads the bind secret
    print('EP3 configuration ready outside Git; existing MySQL users/passwords unchanged.')


def broker_request(method,path,body=None):
    credentials='pedidos360_ep3_admin:'+secret('rabbit-admin')
    request=urllib.request.Request('http://127.0.0.1:15672/api/'+path,
        data=None if body is None else json.dumps(body).encode(),method=method,
        headers={'Authorization':'Basic '+base64.b64encode(credentials.encode()).decode(),'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=10) as response:
        raw=response.read();return json.loads(raw) if raw else None


def configure_broker():
    for role in ('producer','consumer'):
        user='pedidos360_ep3_'+role
        broker_request('PUT','users/'+user,{'password':secret('rabbit-'+role),'tags':''})
        broker_request('PUT','permissions/pedidos360-ep3/'+user,
            {'configure':r'^pedidos360\..*','write':r'^pedidos360\..*','read':r'^pedidos360\..*'})
    print('Dedicated producer/consumer users configured in the isolated EP3 broker/vhost.')


def fingerprint(pid):
    try:
        proc=Path('/proc')/str(pid)
        return {'start':(proc/'stat').read_text().split(') ',1)[1].split()[19],
                'commandHash':hashlib.sha256((proc/'cmdline').read_bytes()).hexdigest()}
    except (FileNotFoundError,ProcessLookupError,PermissionError): return None


def records(): return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
def running(record): return fingerprint(record['pid'])==record['fingerprint']


def stop():
    owned=records()
    for name,record in owned.items():
        if running(record): os.killpg(record['pid'],signal.SIGTERM);print('Stopping EP3 '+name)
    deadline=time.monotonic()+25
    while time.monotonic()<deadline and any(running(r) for r in owned.values()): time.sleep(.2)
    survivors={n:r for n,r in owned.items() if running(r)}
    MANIFEST.write_text(json.dumps(survivors,indent=2))
    if survivors: raise SystemExit('Some owned EP3 processes still stopping; inspect logs')


def start(mode):
    if os.getuid()==0 or os.environ.get('USER')!='codex': raise SystemExit('Run the EP3 runtime as WSL user codex')
    if mode not in ('local','entra'): raise SystemExit('Mode must be local or entra')
    if any(running(r) for r in records().values()): raise SystemExit('EP3 already running; use status/stop')
    if not (CONFIG/'components.json').exists(): raise SystemExit('Run ep3.sh setup first')
    native={name:shutil.which(name) for name in ('java','node')}
    if any(not path or path.startswith('/mnt/') for path in native.values()): raise SystemExit('Native Linux Java/Node required')
    components=json.loads((CONFIG/'components.json').read_text())
    names=(['identity'] if mode=='local' else [])+['catalog-service','orders-service','bff','receipts-service','rabbit-admin-service','frontend']
    for name in names:
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',PORTS[name]))==0: raise SystemExit(f'Occupied port {PORTS[name]}: nothing started')
    common=entra_environment() if mode=='entra' else {'VITE_AUTH_MODE':'local'}
    common['SPRING_PROFILES_ACTIVE']=mode+',ep3'
    common.update(RABBIT_HOST='127.0.0.1',RABBIT_PORT='5672',RABBIT_VHOST='pedidos360-ep3')
    processes={}; owned={}
    try:
        for name in names:
            cwd=ROOT
            env={**os.environ,**common,**components.get(name,{})}
            if name=='identity': command=[native['node'],str(ROOT/'scripts/local-identity.mjs'),'serve']
            elif name=='frontend':
                cwd=Path.home()/'.cache/pedidos360-ep3/frontend'
                env.update(VITE_API_BASE_URL='http://127.0.0.1:19180/api/v1')
                command=[native['node'],str(cwd/'node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port','5173','--strictPort']
            else:
                env['SERVER_PORT']=str(PORTS[name]);env['SERVER_ADDRESS']='127.0.0.1'
                # Same safe HTTP evidence as the previous launcher: no headers,
                # query parameters, bodies, tokens or browser-session access.
                env.update(SERVER_TOMCAT_ACCESSLOG_ENABLED='true',
                    SERVER_TOMCAT_ACCESSLOG_DIRECTORY=str(STATE/'http'),
                    SERVER_TOMCAT_ACCESSLOG_PREFIX=f'{name}-access.',
                    SERVER_TOMCAT_ACCESSLOG_PATTERN='%t %m %U %s %D',
                    SERVER_TOMCAT_ACCESSLOG_BUFFERED='false')
                build=Path(os.environ.get('PEDIDOS_EP3_BUILD_ROOT',Path.home()/'.cache/pedidos360-ep3/build'))
                command=[native['java'],'--enable-native-access=ALL-UNNAMED','-Djava.net.preferIPv4Stack=true','-Xms32m','-Xmx256m','-jar',str(build/name/f'{name}-0.1.0-SNAPSHOT.jar')]
            with (STATE/(name+'.log')).open('w') as log:
                process=subprocess.Popen(command,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            processes[name]=process;owned[name]={'pid':process.pid,'fingerprint':fingerprint(process.pid),'port':PORTS[name],'mode':mode}
            MANIFEST.write_text(json.dumps(owned,indent=2))
        pending=set(names);deadline=time.monotonic()+120
        while pending and time.monotonic()<deadline:
            for name in list(pending):
                if processes[name].poll() is not None: raise RuntimeError(name+' exited; inspect '+str(STATE/(name+'.log')))
                path='/' if name=='frontend' else '/health' if name=='identity' else '/actuator/health'
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{PORTS[name]}{path}',timeout=1) as response:
                        if response.status==200:
                            owned[name]['fingerprint']=fingerprint(owned[name]['pid']);pending.remove(name)
                            print(f'READY EP3 {name}: http://127.0.0.1:{PORTS[name]}',flush=True)
                except (OSError,urllib.error.HTTPError): pass
            if pending: time.sleep(.5)
        if pending: raise RuntimeError('Health timeout: '+','.join(pending))
        MANIFEST.write_text(json.dumps(owned,indent=2));print('EP3 mode: '+mode)
    except BaseException:
        for name,process in processes.items():
            if process.poll() is None: owned[name]['fingerprint']=fingerprint(process.pid)
        MANIFEST.write_text(json.dumps(owned,indent=2));stop();raise


if __name__=='__main__':
    os.umask(0o077)
    action=sys.argv[1] if len(sys.argv)>1 else 'status'
    if action=='setup': setup()
    elif action=='configure-broker': configure_broker()
    elif action=='start': start(sys.argv[2] if len(sys.argv)>2 else 'local')
    elif action=='stop': stop()
    elif action=='status':
        for name,record in records().items(): print(f"{name}: {'RUNNING' if running(record) else 'STOPPED'} port={record['port']} mode={record['mode']}")
    else: raise SystemExit('Unknown EP3 action')
