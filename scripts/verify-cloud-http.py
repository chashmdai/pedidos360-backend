"""Actual public HTTP API negative/CORS checks. Never prints Authorization values."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parent.parent
config=json.loads((ROOT/'config/aws-public.json').read_text())
base=config['apiEndpoint']
assert base==f"https://{config['apiId']}.execute-api.us-east-1.amazonaws.com"
checks=[]


def check(path,method='GET',headers=None,expected=401,case='no_token'):
    time.sleep(.25)  # Remain below the approved small lab throttle.
    request=urllib.request.Request(base+path,method=method,headers=headers or {})
    try:
        response=urllib.request.urlopen(request,timeout=20)
    except urllib.error.HTTPError as error:
        response=error
    with response:
        result={'case':case,'method':method,'path':path,'expected':expected,'status':response.status,'requestId':response.headers.get('apigw-requestid') or response.headers.get('x-amzn-requestid')}
        checks.append(result)
        assert response.status==expected,result
        return response.headers


paths=[('/api/v1/productos','GET'),('/api/v1/productos/1','GET'),('/api/v1/pedidos','GET'),('/api/v1/pedidos/00000000-0000-0000-0000-000000000000','GET'),('/api/v1/pedidos','POST'),('/api/v1/me','GET'),('/api/v1/admin/pedidos','GET')]
for path,method in paths:
    check(path,method)
    check(path,method,{'Authorization':'Bearer invalid.jwt.value'},case='malformed_token')
fixture=subprocess.check_output(['node','scripts/local-identity.mjs','token'],cwd=ROOT,text=True).strip()
check('/api/v1/me',headers={'Authorization':'Bearer '+fixture},case='local_fixture_rejected')
check('/actuator/health',expected=404,case='actuator_not_exposed')
for origin in ['http://localhost:5173','http://127.0.0.1:5173']:
    headers=check('/api/v1/pedidos','OPTIONS',{'Origin':origin,'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'authorization,content-type'},expected=204,case='allowed_preflight')
    assert headers.get('Access-Control-Allow-Origin')==origin
    assert not headers.get('Access-Control-Allow-Credentials')
    assert {'get','post','options'}<=set(headers.get('Access-Control-Allow-Methods','').lower().replace(' ','').split(','))
headers=check('/api/v1/pedidos','OPTIONS',{'Origin':'https://untrusted.invalid','Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'authorization'},expected=204,case='untrusted_origin_no_cors_permission')
assert headers.get('Access-Control-Allow-Origin') is None
report={'at':datetime.now(timezone.utc).isoformat(),'endpoint':base,'checks':checks,'passed':len(checks),'note':'Negative and CORS requests executed over verified HTTPS. No valid Microsoft token used here; real browser tests are recorded separately.'}
destination=ROOT/'docs/evidence/phase5/cloud-http-negative.json'
destination.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
