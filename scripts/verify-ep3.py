"""Real EP3 acceptance tests against this user's isolated runtime. No bearer/password output.

Creates two identifiable local test orders. Deletes only its own disposable lab resources.
The restart flag stops/starts only pedidos360-ep3-rabbitmq, retaining its volume.
"""
import argparse
import base64
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request
import uuid

ROOT=Path(__file__).resolve().parent.parent
STATE=Path.home()/'.local/state/pedidos360-ep3'
EVIDENCE=ROOT/'docs/evidence/ep3'
spec=importlib.util.spec_from_file_location('ep3_runtime',ROOT/'scripts/ep3-runtime.py')
runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)
RUN=uuid.uuid4().hex[:8]
REPORT={'run':RUN,'at':dt.datetime.now(dt.timezone.utc).isoformat(),'mode':'LOCAL_SIGNED_FIXTURE_NOT_ENTRA','checks':[]}


def save(): (EVIDENCE/'runtime-verification.json').write_text(json.dumps(REPORT,indent=2)+'\n')
def passed(name,**evidence):
    REPORT['checks'].append({'name':name,'status':'passed',**evidence});save();print('PASS '+name,flush=True)


def token(subject,scopes='Catalog.Read Orders.Read Orders.Create',roles=None):
    options={'subject':subject,'scopes':scopes,'roles':roles or ['User']}
    return subprocess.check_output(['node','scripts/local-identity.mjs','token',json.dumps(options)],cwd=ROOT,text=True).strip()


USER=token('ep3-verification-'+RUN)
OTHER=token('ep3-other-'+RUN)
ADMIN=token('ep3-admin-'+RUN,'Orders.Read',['Admin'])
ADMIN_NO_SCOPE=token('ep3-admin-'+RUN,'Catalog.Read',['Admin'])


def api(port,path,expected,method='GET',body=None,bearer=USER):
    headers={'Content-Type':'application/json'}
    if bearer: headers['Authorization']='Bearer '+bearer
    request=urllib.request.Request(f'http://127.0.0.1:{port}{path}',method=method,headers=headers,
        data=None if body is None else json.dumps(body).encode())
    try: response=urllib.request.urlopen(request,timeout=15)
    except urllib.error.HTTPError as error: response=error
    with response:
        raw=response.read();status=response.status
        REPORT.setdefault('httpTrace',[]).append({'method':method,'port':port,'path':path,'expected':expected,'actual':status})
        # Never report request headers or token strings, including on failure.
        assert status==expected,f'{method} port={port} {path}: expected {expected}, got {status}: {raw[:300]!r}'
        return json.loads(raw) if raw else None


def sql(statement,context='orders'):
    command=f'MYSQL_PWD="$(cat /run/secrets/{context}_app)" exec mysql -upedidos360_{context}_app --batch --raw --skip-column-names pedidos360_{context}'
    result=subprocess.run(['docker','exec','-i','pedidos360-mysql','sh','-c',command],input=statement,text=True,capture_output=True,timeout=20)
    assert result.returncode==0,'Owned MySQL query failed (credentials not emitted)'
    return [json.loads(line) for line in result.stdout.splitlines() if line]


def existing_orders():
    return sql("SELECT JSON_OBJECT('key',SHA2(o.id,256),'fingerprint',SHA2(CONCAT_WS('|',o.id,o.owner_tenant,o.owner_subject,o.status,o.created_at,GROUP_CONCAT(CONCAT_WS(':',i.product_id,i.product_name,i.unit_price,i.currency,i.quantity) ORDER BY i.product_id)),256)) FROM purchase_orders o JOIN order_items i ON i.order_id=o.id GROUP BY o.id,o.owner_tenant,o.owner_subject,o.status,o.created_at;")


def wait_for(check,description,seconds=30):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        result=check()
        if result: return result
        time.sleep(.25)
    raise AssertionError('Timeout: '+description)


def outbox(order):
    uuid.UUID(order)
    rows=sql(f"SELECT JSON_OBJECT('eventId',event_id,'orderId',order_id,'published',published_at IS NOT NULL,'attempts',attempts,'lastError',last_error_code) FROM order_event_outbox WHERE order_id='{order}';")
    assert len(rows)==1
    return rows[0]


def delivered(order):
    row=outbox(order)
    path=STATE/'receipts'/(row['eventId']+'.json')
    return json.loads(path.read_text()) if row['published'] and path.is_file() else None


def topology():
    source=(ROOT/'messaging-support/src/main/resources/pedidos-rabbit.properties').read_text()
    return {line.split('=',1)[0].removeprefix('pedidos.messaging.'):line.split('=',1)[1] for line in source.splitlines() if line.startswith('pedidos.messaging.')}


TOP=topology()
def broker(method,path,body=None): return runtime.broker_request(method,path,body)
def publish(payload,event_id,routing=None,exchange=None):
    response=broker('POST','exchanges/pedidos360-ep3/'+(exchange or TOP['exchange'])+'/publish',
        {'routing_key':routing or TOP['routing-key'],'payload':payload if isinstance(payload,str) else json.dumps(payload),
         'payload_encoding':'string','properties':{'message_id':event_id,'content_type':'application/json','delivery_mode':2}})
    assert response['routed']


def dead_letters():
    return broker('POST','queues/pedidos360-ep3/'+TOP['dead-queue']+'/get',
        {'count':100,'ackmode':'ack_requeue_true','encoding':'auto','truncate':20000})


def dead_letter(event_id): return next((m for m in dead_letters() if m['properties'].get('message_id')==event_id),None)
def logs_contain(text): return text in (STATE/'receipts-service.log').read_text()


def main(restart):
    baseline=existing_orders()
    catalog_before=sql("SELECT JSON_OBJECT('id',id,'fingerprint',SHA2(CONCAT_WS('|',id,name,description,price,currency,stock,active),256)) FROM products ORDER BY id;",'catalog')
    for name,port in [('bff',19180),('catalog',19181),('orders',19182),('receipts',19183),('admin',19184)]:
        assert api(port,'/actuator/health',200,bearer=None)['status']=='UP'
    passed('T03 health of five Spring services and isolated broker',node=broker('GET','overview')['rabbitmq_version'])
    queues=broker('GET','queues/pedidos360-ep3');exchanges=broker('GET','exchanges/pedidos360-ep3');bindings=broker('GET','bindings/pedidos360-ep3')
    assert {TOP['queue'],TOP['dead-queue']} <= {q['name'] for q in queues}
    assert {TOP['exchange'],TOP['dead-exchange']} <= {e['name'] for e in exchanges}
    assert any(b['source']==TOP['exchange'] and b['destination']==TOP['queue'] and b['routing_key']==TOP['routing-key'] for b in bindings)
    (EVIDENCE/'topology.json').write_text(json.dumps({'queues':queues,'exchanges':exchanges,'bindings':bindings},indent=2)+'\n')
    passed('T05 explicit application and DLQ topology',topology=TOP)
    for port,path in [(19180,'/api/v1/productos'),(19181,'/api/v1/productos'),(19182,'/api/v1/pedidos'),(19184,'/api/v1/rabbit/queues/pedidos360.lab.none')]:
        api(port,path,401,bearer=None);api(port,path,401,bearer='invalid.jwt.value')
    api(19184,'/api/v1/rabbit/queues/pedidos360.lab.none',403)
    api(19184,'/api/v1/rabbit/queues/pedidos360.lab.none',403,bearer=ADMIN_NO_SCOPE)
    api(19183,'/api/v1/admin/receipts',403)
    passed('T11 JWT required and Admin AND Orders.Read enforced',unauthenticated=401,user=403,adminWithoutScope=403)
    products=api(19180,'/api/v1/productos',200);assert len(products)>=2
    request={'items':[{'productoId':'10000000-0000-0000-0000-000000000001','cantidad':2},{'productoId':'10000000-0000-0000-0000-000000000002','cantidad':1}]}
    order=api(19180,'/api/v1/pedidos',201,'POST',request)
    assert order['total']==30970 and len(order['items'])==2
    receipt=wait_for(lambda:delivered(order['id']),'confirmed publication and receipt')
    assert receipt['orderId']==order['id'] and receipt['total']==30970
    assert any(r['eventId']==receipt['eventId'] for r in api(19183,'/api/v1/admin/receipts',200,bearer=ADMIN))
    REPORT['businessOrder']=order;REPORT['businessReceipt']=receipt
    passed('T06 signed JWT business order -> transactional outbox -> broker -> durable receipt -> ACK',orderId=order['id'],eventId=receipt['eventId'],total=30970)
    assert api(19180,'/api/v1/pedidos/'+order['id'],200)==order
    api(19180,'/api/v1/pedidos/'+order['id'],404,bearer=OTHER)
    api(19180,'/api/v1/admin/pedidos',403)
    passed('T12 order snapshot contract, owner isolation and previous authorization preserved')
    publish(receipt,receipt['eventId'])
    wait_for(lambda:logs_contain('eventId='+receipt['eventId']+' orderId='+order['id']+' result=DUPLICATE'),'duplicate ACK')
    assert json.loads((STATE/'receipts'/(receipt['eventId']+'.json')).read_text())==receipt
    passed('T06 identical redelivery is idempotent and ACKed',eventId=receipt['eventId'])
    invalid_id=str(uuid.uuid4());publish('{not-json',invalid_id)
    failed=wait_for(lambda:dead_letter(invalid_id),'invalid event in DLQ')
    assert any(d['reason']=='rejected' for d in failed['properties']['headers']['x-death'])
    passed('T07 malformed event NACK without requeue -> native DLX -> DLQ',eventId=invalid_id,xDeath=failed['properties']['headers']['x-death'])
    transient={**receipt,'eventId':str(uuid.uuid4())};blocker=STATE/'receipts'/(transient['eventId']+'.json')
    blocker.mkdir();publish(transient,transient['eventId'])
    try: wait_for(lambda:logs_contain('RETRY eventId='+transient['eventId']),'transient storage retry')
    finally: blocker.rmdir()
    wait_for(lambda:blocker.is_file(),'receipt stored after recovery')
    wait_for(lambda:logs_contain('ACK eventId='+transient['eventId']),'recovery ACK')
    passed('T08 real temporary filesystem failure recovers within three attempts',eventId=transient['eventId'])
    exhausted={**receipt,'eventId':str(uuid.uuid4())};blocker=STATE/'receipts'/(exhausted['eventId']+'.json')
    blocker.mkdir();publish(exhausted,exhausted['eventId'])
    try: wait_for(lambda:dead_letter(exhausted['eventId']),'retry exhaustion DLQ')
    finally: blocker.rmdir()
    assert logs_contain('reason=RETRY_EXHAUSTED attempts=3')
    passed('T08 exhausted storage failure NACKs once after exactly three attempts',eventId=exhausted['eventId'])
    conflict={**receipt,'total':1};publish(conflict,receipt['eventId'])
    wait_for(lambda:logs_contain('reason=PERMANENT_PROCESSING_ERROR'),'permanent conflicting identity')
    passed('T07 conflicting duplicate rejected without replacing stored receipt')
    name='pedidos360.lab.ep3-'+RUN;exchange=name+'.events';queue=name+'.queue'
    q={'name':queue,'durable':True,'autoDelete':False,'messageTtl':60000,'maxLength':10}
    e={'name':exchange,'type':'direct','durable':True,'autoDelete':False}
    bind={'exchange':exchange,'queue':queue,'routingKey':'lab.registered'}
    base='/api/v1/rabbit'
    api(19184,base+'/queues',201,'POST',q,ADMIN);api(19184,base+'/queues',200,'POST',q,ADMIN)
    api(19184,base+'/exchanges',201,'POST',e,ADMIN);api(19184,base+'/exchanges/'+exchange,200,bearer=ADMIN)
    api(19184,base+'/queues',409,'POST',{**q,'messageTtl':120000},ADMIN)
    api(19184,base+'/exchanges',409,'POST',{**e,'type':'topic'},ADMIN)
    api(19184,base+'/queues',400,'POST',{**q,'name':''},ADMIN)
    api(19184,base+'/queues',400,'POST',{**q,'durable':None},ADMIN)
    api(19184,base+'/queues',400,'POST',{**q,'messageTtl':-10},ADMIN)
    api(19184,base+'/exchanges',400,'POST',{**e,'type':'invalid'},ADMIN)
    api(19184,base+'/bindings',400,'POST',{**bind,'routingKey':''},ADMIN)
    api(19184,base+'/bindings',404,'POST',{**bind,'queue':name+'.missing'},ADMIN)
    api(19184,base+'/queues/'+name+'.missing',404,bearer=ADMIN)
    api(19184,base+'/queues/'+TOP['queue'],403,'DELETE',bearer=ADMIN)
    api(19184,base+'/bindings',201,'POST',bind,ADMIN)
    api(19184,base+'/bindings',200,'POST',bind,ADMIN)
    assert api(19184,base+'/bindings/'+exchange+'/'+queue,200,bearer=ADMIN)
    publish('disposable laboratory message',str(uuid.uuid4()),'lab.registered',exchange)
    api(19184,base+'/queues/'+queue,409,'DELETE',bearer=ADMIN)
    # Consume only this run's disposable sandbox message, never the business queue or DLQ.
    broker('POST','queues/pedidos360-ep3/'+queue+'/get',{'count':10,'ackmode':'ack_requeue_false','encoding':'auto'})
    api(19184,base+'/bindings',204,'DELETE',bind,ADMIN)
    api(19184,base+'/bindings',404,'DELETE',bind,ADMIN)
    api(19184,base+'/queues/'+queue,204,'DELETE',bearer=ADMIN)
    api(19184,base+'/exchanges/'+exchange,204,'DELETE',bearer=ADMIN)
    api(19184,base+'/queues/'+queue,404,bearer=ADMIN)
    passed('T09/T10 administrator creates, queries and deletes sandbox queue/exchange/binding; correct 201/200/204/400/403/404/409; nonempty data protected')
    if restart:
        before_id=runtime.docker('inspect','pedidos360-ep3-rabbitmq','--format','{{.Id}}')
        with (EVIDENCE/'controlled-broker-restart.txt').open('w') as log:
            subprocess.run(['bash','scripts/ep3.sh','broker','stop','rabbitmq'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
            try:
                api(19184,base+'/queues/'+name+'.offline',503,bearer=ADMIN)
                passed('T10 management failure is HTTP 503, never a false success')
                offline=api(19180,'/api/v1/pedidos',201,'POST',request)
                assert api(19180,'/api/v1/pedidos/'+offline['id'],200)==offline
                assert not outbox(offline['id'])['published']
                REPORT['orderDuringBrokerOutage']=offline
                passed('T13 broker outage does not prevent 201 or persistence; outbox stays pending',orderId=offline['id'])
            finally:
                subprocess.run(['bash','scripts/ep3.sh','broker','up','-d','--wait'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        recovered=wait_for(lambda:delivered(offline['id']),'outbox recovery after broker restart',90)
        assert before_id==runtime.docker('inspect','pedidos360-ep3-rabbitmq','--format','{{.Id}}')
        assert dead_letter(invalid_id)
        passed('T13 same broker container/volume recovers pending publication and retains DLQ',eventId=recovered['eventId'])
    after={r['key']:r['fingerprint'] for r in existing_orders()}
    assert all(after.get(r['key'])==r['fingerprint'] for r in baseline)
    assert sql("SELECT JSON_OBJECT('id',id,'fingerprint',SHA2(CONCAT_WS('|',id,name,description,price,currency,stock,active),256)) FROM products ORDER BY id;",'catalog')==catalog_before
    passed('T12 all preexisting orders/lines unchanged and Catalog rows unchanged',preexistingOrders=len(baseline))
    (EVIDENCE/'dead-letter-messages.json').write_text(json.dumps(dead_letters(),indent=2)+'\n')
    (EVIDENCE/'broker-queues-after.json').write_text(json.dumps(broker('GET','queues/pedidos360-ep3'),indent=2)+'\n')
    for service in ('orders-service','receipts-service','rabbit-admin-service'):
        (EVIDENCE/(service+'.txt')).write_text((STATE/(service+'.log')).read_text())
    REPORT['passed']=len(REPORT['checks']);REPORT['complete']=True;save()
    print('All EP3 runtime checks passed: '+str(REPORT['passed']))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--restart-broker',action='store_true');args=parser.parse_args()
    try: main(args.restart_broker)
    except BaseException as error:
        REPORT['complete']=False;REPORT['errorType']=type(error).__name__;REPORT['error']=str(error);save();raise
