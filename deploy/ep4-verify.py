"""Current AWS host checks. Adds only uniquely identified diagnostic messages; never purges DLQs."""
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid

assert os.geteuid()==0
ROOT=Path('/opt/pedidos360/current').resolve()
os.environ['PEDIDOS_EP4_CONFIG_DIR']='/etc/pedidos360/ep4'
spec=importlib.util.spec_from_file_location('broker',ROOT/'scripts/ep4-broker.py')
broker=importlib.util.module_from_spec(spec);spec.loader.exec_module(broker)
def http(port,path):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}'+path,timeout=5) as response:return response.status
    except urllib.error.HTTPError as error:return error.code
def wait_for(predicate):
    deadline=time.monotonic()+40
    while time.monotonic()<deadline:
        value=predicate()
        if value:return value
        time.sleep(1)
    raise AssertionError('Expected broker condition timed out')
def main():
    p=broker.topology();n=lambda key:p['pedidos.messaging.'+key]
    v=broker.VHOST
    report={'environment':'AWS EC2 (not WSL)','at':dt.datetime.now(dt.timezone.utc).isoformat(),'release':ROOT.name,'checks':[]}
    clusters={}
    for node in ('pedidos360-ep4-rabbit-1','pedidos360-ep4-rabbit-2'):
        cluster=json.loads(subprocess.check_output(['docker','exec',node,'rabbitmqctl','cluster_status','--formatter=json'],text=True))
        assert set(cluster['running_nodes'])=={'rabbit@pedidos360-ep4-rabbit-1','rabbit@pedidos360-ep4-rabbit-2'}
        assert cluster['partitions']=={} and cluster['alarms']==[]
        clusters[node]={k:cluster[k] for k in ('cluster_name','disk_nodes','running_nodes','partitions','alarms','versions')}
    report['cluster']=clusters
    report['checks'].append('Both nodes report the same two running members, no partitions/alarms')
    expected={n('queue'):n('dead-queue'),n('insights.audit-queue'):n('insights.audit-dead-queue'),n('insights.sales-queue'):n('insights.sales-dead-queue')}
    def queues():return {q['name']:q for q in broker.api('GET','queues/'+v)}
    topology=wait_for(lambda:queues() if all(queues().get(q,{}).get('consumers')==1 for q in expected) else None)
    assert set(topology)==set(expected)|set(expected.values())
    report['queuesBefore']=[{k:q.get(k) for k in ('name','type','node','durable','arguments','consumers','messages','messages_ready','messages_unacknowledged')} for q in topology.values()]
    exchanges=broker.api('GET','exchanges/'+v)
    assert any(x['name']==n('exchange') and x['type']=='direct' for x in exchanges)
    assert any(x['name']==n('insights.topic-exchange') and x['type']=='topic' for x in exchanges)
    report['exchanges']=[{k:x[k] for k in ('name','type','durable')} for x in exchanges if x['name'].startswith('pedidos360.')]
    report['bindings']=[b for b in broker.api('GET','bindings/'+v) if b['source'].startswith('pedidos360.')]
    report['checks'].append('Three live consumers, three separate DLQs, production direct/topic bindings')
    baseline={q:topology[q].get('messages',0) for q in expected.values()}
    def publish(exchange,key,label):
        event_id=str(uuid.uuid4())
        result=broker.api('POST',f'exchanges/{v}/{exchange}/publish',{'properties':{'delivery_mode':2,'message_id':event_id},
            'routing_key':key,'payload':'{invalid-'+label,'payload_encoding':'string'})
        return {'eventId':event_id,'key':key,'routed':result['routed'],'label':label}
    report['routingTests']=[publish(n('exchange'),n('routing-key'),'all-three-dlq')]
    assert report['routingTests'][0]['routed']
    wait_for(lambda:all(queues()[q].get('messages',0)>=count+1 for q,count in baseline.items()))
    for key,which in [('order.registered.probe','insights.audit-dead-queue'),('probe.registered.v1','insights.sales-dead-queue')]:
        before={q:info.get('messages',0) for q,info in queues().items() if q in expected.values()}
        result=publish(n('insights.topic-exchange'),key,'selective-topic');assert result['routed'];report['routingTests'].append(result)
        target=n(which);wait_for(lambda:queues()[target].get('messages',0)>=before[target]+1)
        assert all(queues()[q].get('messages',0)==count for q,count in before.items() if q!=target)
    for exchange,key in [(n('exchange'),'order.cancelled.v1'),(n('insights.topic-exchange'),'order.cancelled.v1')]:
        result=publish(exchange,key,'unrouted-negative');assert not result['routed'];report['routingTests'].append(result)
    report['checks'].append('Actual direct fanout to three NACK/DLQs; selective wildcard topic routing and negative controls')
    report['deadLetters']={}
    # Read + requeue preserves the diagnostic message and all previous DLQ contents.
    for dlq in expected.values():
        messages=broker.api('POST',f'queues/{v}/{dlq}/get',{'count':1,'ackmode':'ack_requeue_true','encoding':'auto','truncate':0})
        assert messages and any(x['reason']=='rejected' for x in messages[0]['properties']['headers']['x-death'])
        report['deadLetters'][dlq]={'messageId':messages[0]['properties'].get('message_id'),'xDeath':messages[0]['properties']['headers']['x-death']}
    report['unauthenticatedHttp']={}
    for name,port,path in [('bff',8180,'/api/v1/pedidos'),('catalog',8181,'/api/v1/productos'),('orders',8182,'/api/v1/pedidos'),
                           ('receipts',8183,'/api/v1/admin/receipts'),('admin',8184,'/api/v1/rabbit/queues/pedidos360.lab.probe'),('insights',8185,'/api/v1/admin/insights/audit')]:
        status=http(port,path);assert status==401;report['unauthenticatedHttp'][name]=status
    assert http(8180,'/app/')==200 and http(8180,'/app/pedidos')==200
    report['checks'].append('All six services reject missing JWT; cloud SPA served without opening API authorization')
    report['connections']=[{k:c.get(k) for k in ('name','node','user','vhost','state','peer_host')} for c in broker.api('GET','connections') if c['vhost']==v]
    report['compose']=subprocess.check_output(['docker','compose','-f',str(ROOT/'compose.ep4.yaml'),'ps','--format','json'],text=True)
    report['memory']=subprocess.check_output(['free','-m'],text=True)
    print(json.dumps(report))
if __name__=='__main__':main()
