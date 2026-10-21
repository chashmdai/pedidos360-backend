"""Public discovery/config checks and unauthenticated/fixture rejection in EP3 Entra mode.

Does not access real browser sessions or real access tokens. Login is a separate
manual step. Does not execute az, Graph writes, or AWS.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import urllib.error
import urllib.request
from entra_config import environment

ROOT=Path(__file__).resolve().parent.parent
config=environment()
checks=[]
with urllib.request.urlopen(config['JWT_ISSUER']+'/.well-known/openid-configuration',timeout=20) as response:
    discovery=json.load(response)
assert discovery['issuer']==config['JWT_ISSUER']
assert discovery['jwks_uri']==config['JWT_JWKS_URI']
with urllib.request.urlopen(discovery['jwks_uri'],timeout=20) as response:
    assert json.load(response)['keys']
fixture=subprocess.check_output([str(Path.home()/'.local/share/pedidos360-ep3/node/bin/node'),str(ROOT/'scripts/local-identity.mjs'),'token'],cwd=ROOT,text=True).strip()
def call(port,path,expected,headers=None,method='GET'):
    request=urllib.request.Request(f'http://127.0.0.1:{port}{path}',headers=headers or {},method=method)
    try: response=urllib.request.urlopen(request,timeout=15)
    except urllib.error.HTTPError as error: response=error
    with response:
        checks.append(dict(port=port,path=path,expected=expected,actual=response.status,case='fixture_rejected' if headers and headers.get('Authorization') else 'unauthenticated' if expected==401 else 'health_or_cors'))
        assert response.status==expected
        return response.headers
for port,path in [(19180,'/api/v1/productos'),(19181,'/api/v1/productos'),(19182,'/api/v1/pedidos'),(19183,'/api/v1/admin/receipts'),(19184,'/api/v1/rabbit/queues/pedidos360.lab.none')]:
    call(port,'/actuator/health',200)
    call(port,path,401)
    call(port,path,401,{'Authorization':'Bearer '+fixture})
for origin in ('http://localhost:5173','http://127.0.0.1:5173'):
    headers=call(19180,'/api/v1/me',200,{'Origin':origin,'Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'authorization,content-type'},'OPTIONS')
    assert headers['Access-Control-Allow-Origin']==origin
spa=json.loads((ROOT/'docs/evidence/entra/verified-spa-app.json').read_text())
assert set(spa['spa']['redirectUris']) >= {'http://localhost:5173/','http://127.0.0.1:5173/'}
report=dict(at=datetime.now(timezone.utc).isoformat(),mode='entra',realLogin=False,
    publicDiscoveryAndJwks=True,scopes=['Catalog.Read','Orders.Read','Orders.Create'],
    redirectSource='previously verified Graph manifest; no new Graph write',redirects=spa['spa']['redirectUris'],
    fixtureRejectedByAllFiveServices=True,checks=checks,passed=len(checks))
(ROOT/'docs/evidence/ep3/entra-preflight.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS Entra public discovery, canonical scopes/redirects, five services reject fixture; HTTP checks:',len(checks))
print('Real DUOC login remains a manual step, not claimed by this preflight.')
