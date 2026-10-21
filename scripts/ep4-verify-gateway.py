"""Public HTTP probes only; no access tokens or browser sessions are read."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import urllib.request
import urllib.error

ROOT=Path(__file__).resolve().parent.parent
config=json.loads((ROOT/'config/aws-public.json').read_text())
base=config['apiEndpoint']
manifest=json.loads((ROOT/'docs/evidence/ep4/release-manifest.json').read_text())
report={'at':dt.datetime.now(dt.timezone.utc).isoformat(),'environment':'AWS API Gateway HTTPS','checks':[]}
def request(path,expected,invalid=False):
    headers={'Authorization':'Bearer invalid-ep4-probe'} if invalid else {}
    try:
        response=urllib.request.urlopen(urllib.request.Request(base+path,headers=headers),timeout=20)
    except urllib.error.HTTPError as error:response=error
    data=response.read()
    report['checks'].append({'path':path,'status':response.code,'expected':expected,'invalidSyntheticBearer':invalid,
        'requestId':response.headers.get('apigw-requestid') or response.headers.get('x-amzn-requestid'),
        'contentType':response.headers.get('Content-Type'),'sha256':hashlib.sha256(data).hexdigest()})
    assert response.code==expected,report['checks'][-1]
    return data
html=request('/app/',200).decode()
request('/app',200)
request('/app/pedidos',200)
for asset in re.findall(r'(?:src|href)="(/app/assets/[^" ]+)"',html):
    data=request(asset,200)
    assert hashlib.sha256(data).hexdigest()==manifest['files']['frontend/'+asset.removeprefix('/app/')]
    if asset.endswith('.js'):assert b'127.0.0.1:8190' not in data,'Local fixture unexpectedly present in production'
request('/api/v1/productos',401)
request('/api/v1/productos',401,invalid=True)
request('/api/v1/pedidos',401)
report['verifiedFrontendBytesMatchRelease']=True
(ROOT/'docs/evidence/ep4/gateway-http.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
