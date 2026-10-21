"""Correlate a browser-observed order prefix with RDS/outbox/three durable effects. No bearer access."""
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import time

prefix=sys.argv[1];assert re.fullmatch('[0-9a-f]{8}',prefix)
pending_only=len(sys.argv)>2 and sys.argv[2]=='pending'
def environment(context):
    return {k:shlex.split(v)[0] for line in Path('/etc/pedidos360/'+context+'.env').read_text().splitlines() if '=' in line for k,v in [line.split('=',1)]}
def sql(context,query):
    env=environment(context);p=context.upper();host=env[p+'_DB_URL'].split('://',1)[1].split(':',1)[0]
    with tempfile.NamedTemporaryFile(mode='w',suffix='.cnf') as config:
        config.write('[client]\nhost='+host+'\nport=3306\nuser='+env[p+'_DB_USER']+'\npassword='+env[p+'_DB_PASSWORD']+'\nssl-mode=VERIFY_IDENTITY\nssl-ca=/etc/pedidos360/tls/rds-ca-bundle.pem\n');config.flush()
        return subprocess.check_output(['mysql','--defaults-extra-file='+config.name,'--batch','--raw','--skip-column-names','pedidos360_'+context,'-e',query],text=True)
def main():
    rows=sql('orders',"SELECT id,status FROM purchase_orders WHERE id LIKE '"+prefix+"%'").splitlines();assert len(rows)==1
    order_id,status=rows[0].split('\t');assert status=='REGISTERED'
    deadline=time.monotonic()+45
    while True:
        outbox=sql('orders',"SELECT event_id,published_at IS NOT NULL,attempts,COALESCE(last_error_code,''),payload FROM order_event_outbox WHERE order_id='"+order_id+"'").strip().split('\t',4)
        assert len(outbox)==5
        event_id,published,attempts,error,payload=outbox
        if pending_only or published=='1' or time.monotonic()>deadline:break
        time.sleep(1)
    report={'environment':'AWS EC2/RDS + actual cloud UI order','at':dt.datetime.now(dt.timezone.utc).isoformat(),'orderId':order_id,'status':status,
        'outbox':{'eventId':event_id,'published':published=='1','attempts':int(attempts),'errorCode':error},'event':json.loads(payload),'effects':{},'logs':[]}
    if pending_only:
        assert published=='0','Order already published; not an outage observation'
        print(json.dumps(report));return
    assert published=='1'
    paths={'receipt':Path('/var/lib/pedidos360-receipts/receipts'),
           'audit':Path('/var/lib/pedidos360-insights/projections/audit'),'sales':Path('/var/lib/pedidos360-insights/projections/sales')}
    for flow,directory in paths.items():
        file=directory/(event_id+'.json')
        while not file.exists() and time.monotonic()<deadline:time.sleep(1)
        assert file.exists(),'Missing '+flow
        event=json.loads(file.read_text());assert event==json.loads(payload)
        report['effects'][flow]={'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'eventId':event['eventId'],'orderId':event['orderId'],'amount':event['total'],'currency':event['currency']}
    if len(sys.argv)>2 and sys.argv[2]=='duplicate':
        os.environ['PEDIDOS_EP4_CONFIG_DIR']='/etc/pedidos360/ep4'
        spec=importlib.util.spec_from_file_location('broker',Path('/opt/pedidos360/current/scripts/ep4-broker.py'))
        broker=importlib.util.module_from_spec(spec);spec.loader.exec_module(broker)
        names=broker.topology()
        before={flow:len(list(directory.glob('*.json'))) for flow,directory in paths.items()}
        result=broker.api('POST','exchanges/'+broker.VHOST+'/'+names['pedidos.messaging.exchange']+'/publish',
            {'properties':{'delivery_mode':2,'message_id':event_id},'routing_key':names['pedidos.messaging.routing-key'],'payload':payload,'payload_encoding':'string'})
        assert result['routed']
        time.sleep(3)
        for flow,directory in paths.items():
            assert len(list(directory.glob('*.json')))==before[flow]
            assert hashlib.sha256((directory/(event_id+'.json')).read_bytes()).hexdigest()==report['effects'][flow]['sha256']
        report['duplicateTest']={'source':'Management diagnostic republication of the exact stored outbox payload','routed':True,'fileCountsUnchanged':before,'allEffectHashesUnchanged':True}
    for service in ('orders','receipts','insights'):
        log=subprocess.check_output(['journalctl','--unit=pedidos360-'+service,'--no-pager','--lines=600'],text=True)
        report['logs'] += [line[line.index(code):] for line in log.splitlines() if event_id in line for code in ['PUBLISH_CONFIRMED','PUBLISH_DEFERRED','ACK flow=','ACK eventId='] if code in line]
    assert any(line.startswith('PUBLISH_CONFIRMED') for line in report['logs'])
    assert any('ACK eventId=' in line for line in report['logs'])
    assert any('ACK flow=audit' in line for line in report['logs']) and any('ACK flow=sales' in line for line in report['logs'])
    if 'duplicateTest' in report:
        assert any('ACK eventId=' in line and 'DUPLICATE' in line for line in report['logs'])
        assert all(any('ACK flow='+flow in line and 'DUPLICATE' in line for line in report['logs']) for flow in ('audit','sales'))
    baseline=json.loads(Path('/var/lib/pedidos360-provision/ep4-data-baseline.json').read_text())
    report['previousDataPreserved']={}
    for table,old in baseline.items():
        context,name=table.split('.')
        actual={line.split('\t',1)[0]:hashlib.sha256(line.encode()).hexdigest() for line in sql(context,'SELECT * FROM '+name+' ORDER BY id').splitlines()}
        assert all(actual.get(key)==value for key,value in old.items()),'Previous data modified: '+table
        report['previousDataPreserved'][table]={'previousRows':len(old),'currentRows':len(actual),'allPreviousHashesUnchanged':True}
    print(json.dumps(report))
if __name__=='__main__':main()
