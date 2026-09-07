"""Read-only SQL and HTTP evidence for the single browser-created cloud test order."""
import datetime as dt
import json
from pathlib import Path
import subprocess
import tempfile

current=Path('/opt/pedidos360/current').resolve()
manifest=json.loads((current/'manifest.json').read_text())
env=dict(line.split('=',1) for line in Path('/etc/pedidos360/orders.env').read_text().splitlines() if '=' in line)
env={key:value.strip('"') for key,value in env.items()}
password=env['ORDERS_DB_PASSWORD']
sql="""SELECT JSON_OBJECT('id',o.id,'tenant',o.owner_tenant,'owner',o.owner_subject,
'status',o.status,'createdAt',o.created_at,'total',SUM(i.unit_price*i.quantity),
'items',JSON_ARRAYAGG(JSON_OBJECT('productId',i.product_id,'name',i.product_name,
'price',i.unit_price,'currency',i.currency,'quantity',i.quantity)))
FROM pedidos360_orders.purchase_orders o JOIN pedidos360_orders.order_items i ON i.order_id=o.id
WHERE o.id LIKE '9f82f14f%' GROUP BY o.id,o.owner_tenant,o.owner_subject,o.status,o.created_at;
"""
with tempfile.NamedTemporaryFile(mode='w',suffix='.cnf') as config:
    config.write(f"[client]\nhost={manifest['rdsEndpoint']}\nuser={env['ORDERS_DB_USER']}\npassword={password}\nssl-mode=VERIFY_IDENTITY\nssl-ca=/etc/pedidos360/tls/rds-ca-bundle.pem\nconnect-timeout=10\n")
    config.flush()
    result=subprocess.run(['mysql','--defaults-extra-file='+config.name,'--batch','--raw','--skip-column-names'],input=sql,text=True,capture_output=True,timeout=30)
if result.returncode:
    raise RuntimeError(result.stderr.replace(password,'[REDACTED]'))
orders=[json.loads(line) for line in result.stdout.splitlines() if line]
assert len(orders)==1,'Expected exactly the browser test order'
order=orders[0]
assert order['tenant']==manifest['entra']['tenantId']
assert order['owner']=='c375a6eb-b82a-44f6-abe0-fe32d7901c3e'
assert order['status']=='REGISTERED' and order['total']==30970 and len(order['items'])==2
assert sorted((item['price'],item['quantity'],item['currency']) for item in order['items'])==[(8990,2,'CLP'),(12990,1,'CLP')]
logs={}
for context in ('bff','catalog','orders'):
    lines=[]
    for file in sorted(Path('/var/log/pedidos360',context).glob('*')):
        if file.is_file():
            lines.extend(line for line in file.read_text().splitlines() if '/api/v1/' in line)
    logs[context]=lines[-150:]
report={'at':dt.datetime.now(dt.timezone.utc).isoformat(),'release':manifest['release'],'order':order,'accessLogs':logs,'note':'Direct TLS SQL read of the browser-created test order; HTTP access logs omit query, headers and body.'}
print(json.dumps(report,indent=2))
