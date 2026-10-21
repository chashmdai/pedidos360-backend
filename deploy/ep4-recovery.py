"""Controlled outage of the TWO OWN EP4 nodes; keep containers, volumes and every message."""
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

assert os.geteuid()==0
mode=sys.argv[1];assert mode in ('stop','start')
ROOT=Path('/opt/pedidos360/current').resolve()
os.environ['PEDIDOS_EP4_CONFIG_DIR']='/etc/pedidos360/ep4'
spec=importlib.util.spec_from_file_location('broker',ROOT/'scripts/ep4-broker.py')
broker=importlib.util.module_from_spec(spec);spec.loader.exec_module(broker)
nodes=['pedidos360-ep4-rabbit-1','pedidos360-ep4-rabbit-2']
state=Path('/var/lib/pedidos360-provision/ep4-recovery-baseline.json')
def containers():
    items=json.loads(subprocess.check_output(['docker','inspect',*nodes],text=True))
    result={}
    for item in items:
        assert item['Config']['Labels']['Project']=='Pedidos360' and item['Config']['Labels']['Purpose']=='ep4'
        result[item['Name'].lstrip('/') ]={'id':item['Id'],'volumes':[v['Name'] for v in item['Mounts'] if v['Type']=='volume']}
    return result
def files():
    dirs=[Path('/var/lib/pedidos360-receipts/receipts'),Path('/var/lib/pedidos360-insights/projections')]
    return {str(file):hashlib.sha256(file.read_bytes()).hexdigest() for directory in dirs for file in directory.rglob('*.json')}
if mode=='stop':
    assert not state.exists(),'An outage baseline exists: inspect it, never replace it automatically'
    before={'at':dt.datetime.now(dt.timezone.utc).isoformat(),'containers':containers(),'files':files(),
        'dlqCounts':{q['name']:q['messages'] for q in broker.api('GET','queues/'+broker.VHOST) if q['name'].endswith('.failed.v1')}}
    state.write_text(json.dumps(before))
    subprocess.run(['docker','stop','--time','30',*nodes],check=True,capture_output=True)
    print(json.dumps({'at':dt.datetime.now(dt.timezone.utc).isoformat(),'environment':'AWS EC2','action':'stopped only the two owned EP4 nodes','preserved':before}))
else:
    before=json.loads(state.read_text())
    subprocess.run(['docker','compose','-f',str(ROOT/'compose.ep4.yaml'),'up','-d','--wait','--wait-timeout','240'],check=True,capture_output=True)
    after=containers();assert after==before['containers'],'Unexpected container or volume replacement'
    current=files();assert all(current.get(path)==digest for path,digest in before['files'].items())
    deadline=time.monotonic()+90
    while True:
        queues=broker.api('GET','queues/'+broker.VHOST)
        active={q['name']:q['consumers'] for q in queues if not q['name'].endswith('.failed.v1')}
        if len(active)==3 and all(count==1 for count in active.values()):break
        assert time.monotonic()<deadline,'Consumers did not reconnect';time.sleep(1)
    counts={q['name']:q['messages'] for q in queues if q['name'].endswith('.failed.v1')}
    assert counts==before['dlqCounts'],'Previously confirmed DLQ messages changed'
    cluster=json.loads(subprocess.check_output(['docker','exec',nodes[0],'rabbitmqctl','cluster_status','--formatter=json'],text=True))
    assert set(cluster['running_nodes'])=={'rabbit@'+n for n in nodes}
    print(json.dumps({'at':dt.datetime.now(dt.timezone.utc).isoformat(),'environment':'AWS EC2','action':'recovered through Docker Compose',
        'sameContainerAndVolumeIds':True,'previousFilesUnchanged':len(before['files']),'dlqCountsBefore':before['dlqCounts'],
        'dlqCountsAfter':counts,'consumers':active,'clusterMembers':cluster['running_nodes'],'partitions':cluster['partitions']}))
