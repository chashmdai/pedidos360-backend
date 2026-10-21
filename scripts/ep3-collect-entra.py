"""Correlate a browser-created Entra order without reading any browser token/session."""
from datetime import datetime, timezone
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import time

ROOT=Path(__file__).resolve().parent.parent
E=ROOT/'docs/evidence/ep3'
STATE=Path.home()/'.local/state/pedidos360-ep3'

def sql(statement):
    command='MYSQL_PWD="$(cat /run/secrets/orders_app)" exec mysql -upedidos360_orders_app --batch --raw --skip-column-names pedidos360_orders'
    result=subprocess.run(['docker','exec','-i','pedidos360-mysql','sh','-c',command],input=statement,text=True,capture_output=True,timeout=20)
    assert result.returncode==0,'Owned MySQL read failed; credentials suppressed'
    return [json.loads(line) for line in result.stdout.splitlines() if line]

def main(prefix):
    assert re.fullmatch('[0-9a-fA-F]{8}',prefix),'Use the eight hex characters visible in the UI'
    processes=json.loads((STATE/'processes.json').read_text())
    assert all(p['mode']=='entra' for p in processes.values())
    rows=sql("SELECT JSON_OBJECT('orderId',o.id,'eventId',e.event_id,'published',e.published_at IS NOT NULL,'payload',e.payload,'createdAt',o.created_at) FROM purchase_orders o JOIN order_event_outbox e ON e.order_id=o.id WHERE o.id LIKE '"+prefix.lower()+"%';")
    assert len(rows)==1
    row=rows[0]; payload=row.pop('payload')
    if isinstance(payload,str): payload=json.loads(payload)
    receipt_file=STATE/'receipts'/(row['eventId']+'.json')
    deadline=time.monotonic()+30
    while not receipt_file.is_file() and time.monotonic()<deadline:time.sleep(.25)
    receipt=json.loads(receipt_file.read_text())
    assert row['published'] and receipt==payload
    assert receipt['total']==30970 and receipt['itemCount']==2
    claims=json.loads((E/'entra-validated-claims.json').read_text())
    assert claims['role']=='User' and all(scope in claims['Permisos de la API'] for scope in ('Catalog.Read','Orders.Read','Orders.Create'))
    http={}
    for name in ('bff','catalog-service','orders-service','receipts-service','rabbit-admin-service'):
        lines=[]
        for file in sorted((STATE/'http').glob(name+'-access.*.log')):
            lines+=file.read_text().splitlines()
        # Pattern contains time, verb, URL path and status only; no identity/headers.
        business=[line for line in lines if '/api/v1/' in line]
        (E/('entra-'+name+'-http.txt')).write_text('\n'.join(business)+'\n')
        http[name]=business
    bff='\n'.join(http['bff']);orders='\n'.join(http['orders-service'])
    assert 'POST /api/v1/pedidos 201 ' in bff and 'POST /api/v1/pedidos 201 ' in orders
    assert 'GET /api/v1/productos 200 ' in bff
    assert 'GET /api/v1/pedidos 200 ' in bff
    assert 'GET /api/v1/admin/pedidos 403 ' in bff
    assert bff.count('GET /api/v1/me 200 ')>=2
    logs={}
    for service,marker in (('orders-service','PUBLISH_CONFIRMED'),('receipts-service','ACK eventId=')):
        selected=[line for line in (STATE/(service+'.log')).read_text().splitlines() if row['eventId'] in line]
        assert any(marker in line for line in selected)
        logs[service]=selected
        (E/('entra-'+service+'-event.txt')).write_text('\n'.join(selected)+'\n')
    report=dict(at=datetime.now(timezone.utc).isoformat(),mode='MICROSOFT_ENTRA_REAL',
        authentication='Manual DUOC login and MFA completed by user; no tokens or browser sessions read/exported',
        principalRole='User',scopes=['Catalog.Read','Orders.Read','Orders.Create'],
        http={'catalog':200,'createOrder':201,'listOrdersAfterReload':200,'adminUserDenied':403,'meAfterRequestedRefresh':200},
        tokenRefresh='MSAL forceRefresh requested; accepted by BFF. Natural expiration was not tested.',
        order=row,receipt=receipt,publisherAndConsumerLogs=logs,temporaryAdminAssignment=False,
        noEntraWrites=True,noAwsOperations=True)
    (E/'entra-verification.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    manifest=json.loads((E/'captures.json').read_text())
    for file in sorted(E.glob('*-entra-*.png')):
        manifest=[m for m in manifest if m['file']!=file.name]
        manifest.append(dict(file=file.name,source='http://localhost:5173 (Entra real)',description='Pantalla real mediante navegador integrado; sin credenciales ni tokens',at=datetime.fromtimestamp(file.stat().st_mtime,timezone.utc).isoformat(),sha256=hashlib.sha256(file.read_bytes()).hexdigest()))
    (E/'captures.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    print('PASS real Entra: Catalog 200, POST 201, GET after reload 200, Admin 403, refresh accepted, outbox confirmed, receipt + ACK')
    print('orderId='+row['orderId']+' eventId='+row['eventId'])

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('prefix');args=parser.parse_args();main(args.prefix)
