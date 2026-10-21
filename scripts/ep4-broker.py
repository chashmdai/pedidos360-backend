"""Own EP4 cluster only. Also used on the dedicated EC2; no prune/down/delete commands."""
import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.request
import urllib.parse

ROOT=Path(__file__).resolve().parent.parent
CONFIG=Path(os.environ.get('PEDIDOS_EP4_CONFIG_DIR',Path.home()/'.config/pedidos360/ep4'))
VHOST='pedidos360-ep4'
def topology():
    return dict(line.split('=',1) for line in (ROOT/'messaging-support/src/main/resources/pedidos-rabbit.properties').read_text().splitlines()
        if line.startswith('pedidos.messaging.') and '=' in line)
def api(method,path,body=None):
    password=(CONFIG/'rabbit-admin-password').read_text().strip()
    request=urllib.request.Request('http://127.0.0.1:15674/api/'+path,
        data=json.dumps(body).encode() if body is not None else None,method=method,
        headers={'Authorization':'Basic '+base64.b64encode(('pedidos360_ep4_admin:'+password).encode()).decode(),'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=30) as response:
        text=response.read();return json.loads(text) if text else None
def configure():
    p=topology();n=lambda key:p['pedidos.messaging.'+key]
    v=urllib.parse.quote(VHOST,safe='')
    exchanges={n('exchange'):'direct',n('dead-exchange'):'direct',n('insights.topic-exchange'):'topic',n('insights.audit-dead-exchange'):'direct',n('insights.sales-dead-exchange'):'direct'}
    for name,kind in exchanges.items(): api('PUT',f'exchanges/{v}/{name}',{'type':kind,'durable':True,'auto_delete':False,'internal':False,'arguments':{}})
    flows=[(n('queue'),n('dead-exchange'),n('dead-routing-key'),n('dead-queue'),n('exchange'),n('routing-key')),
           (n('insights.audit-queue'),n('insights.audit-dead-exchange'),n('insights.audit-dead-key'),n('insights.audit-dead-queue'),n('insights.topic-exchange'),n('insights.audit-pattern')),
           (n('insights.sales-queue'),n('insights.sales-dead-exchange'),n('insights.sales-dead-key'),n('insights.sales-dead-queue'),n('insights.topic-exchange'),n('insights.sales-pattern'))]
    for queue,dlx,key,dlq,exchange,pattern in flows:
        for name,arguments in ((queue,{'x-queue-type':'classic','x-dead-letter-exchange':dlx,'x-dead-letter-routing-key':key}),(dlq,{'x-queue-type':'classic'})):
            api('PUT',f'queues/{v}/{name}',{'durable':True,'auto_delete':False,'arguments':arguments})
        for ex,q,k in ((exchange,queue,pattern),(dlx,dlq,key)):
            api('POST',f'bindings/{v}/e/{ex}/q/{q}',{'routing_key':k,'arguments':{}})
    api('POST',f'bindings/{v}/e/{n("exchange")}/e/{n("insights.topic-exchange")}',{'routing_key':n('routing-key'),'arguments':{}})
    for role in ('producer','consumer'):
        user='pedidos360_ep4_'+role
        api('PUT','users/'+user,{'password':(CONFIG/('rabbit-'+role+'-password')).read_text().strip(),'tags':''})
        queues='^('+ '|'.join(q[0].replace('.','\\.') for q in flows)+')$'
        api('PUT',f'permissions/{v}/{user}',{'configure':'^$','write':'^'+n('exchange').replace('.','\\.')+'$' if role=='producer' else '^$',
            'read':queues if role=='consumer' else '^$'})
    return {'exchanges':api('GET','exchanges/'+v),'queues':api('GET','queues/'+v),'bindings':api('GET','bindings/'+v),'nodes':api('GET','nodes')}
def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['up','status','configure']);args=parser.parse_args()
    os.umask(0o077);CONFIG.mkdir(parents=True,exist_ok=True,mode=0o700)
    if args.action=='up':
        for name in ('rabbit-admin-password','rabbit-producer-password','rabbit-consumer-password','rabbit-cookie'):
            path=CONFIG/name
            if not path.exists():
                # Do not replace lost secrets for volumes already containing a cluster.
                for volume in ('pedidos360-ep4-rabbit-1-data','pedidos360-ep4-rabbit-2-data'):
                    if subprocess.run(['docker','volume','inspect',volume],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:
                        raise SystemExit('Existing EP4 volume but missing secret; recover configuration, never reset it')
                path.write_text(secrets.token_hex(32));path.chmod(0o600)
        env={**os.environ,'PEDIDOS_EP4_CONFIG_DIR':str(CONFIG)}
        subprocess.run(['docker','compose','-f',str(ROOT/'compose.ep4.yaml'),'up','-d','--wait','--wait-timeout','240'],env=env,check=True)
        configure()
    elif args.action=='configure': configure()
    cluster=subprocess.run(['docker','exec','pedidos360-ep4-rabbit-1','rabbitmqctl','cluster_status','--formatter=json'],capture_output=True,text=True,check=True)
    status=json.loads(cluster.stdout)
    assert set(status['running_nodes'])=={'rabbit@pedidos360-ep4-rabbit-1','rabbit@pedidos360-ep4-rabbit-2'},status
    print(json.dumps({'cluster':status,'resources':{'queues':api('GET','queues/'+VHOST),'bindings':api('GET','bindings/'+VHOST),'exchanges':api('GET','exchanges/'+VHOST)}},indent=2))
if __name__=='__main__':main()
