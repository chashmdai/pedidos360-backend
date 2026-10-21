"""Add only public GET SPA paths to the existing HTTP API. Preserve all JWT API routes."""
import json
from pathlib import Path
import aws_deploy as aws

OUT=aws.ROOT/'docs/evidence/ep4'
aws.PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700)
identity=aws.call('sts','get-caller-identity');assert identity['Account']==aws.ACCOUNT and '/voclabs/' in identity['Arn']
old=json.loads(aws.JOURNAL.read_text())['steps']
api_id=old['http-api']['response']['ApiId'];integration=old['integration']['response']['IntegrationId']
api=aws.call('apigatewayv2','get-api',{'ApiId':api_id})
assert api['Name']=='pedidos360-http-api' and api['Tags']['Project']=='Pedidos360'
before=aws.call('apigatewayv2','get-routes',{'ApiId':api_id})['Items']
original_ids={old['route-'+str(i)]['response']['RouteId'] for i in range(7)}
assert original_ids.issubset({route['RouteId'] for route in before})
journal=OUT/'gateway-journal.json'
state=json.loads(journal.read_text()) if journal.exists() else {'account':aws.ACCOUNT,'apiId':api_id,'steps':{}}
for key in ('GET /app','GET /app/{proxy+}'):
    existing=next((route for route in before if route['RouteKey']==key),None)
    if existing:
        assert existing['AuthorizationType']=='NONE' and existing['Target']=='integrations/'+integration
        state['steps'][key]={'status':'verified-existing','routeId':existing['RouteId']};continue
    if key in state['steps']:
        raise SystemExit('Interrupted/recorded route: reconcile before retry '+key)
    state['steps'][key]={'status':'in-progress','at':aws.now()};aws.save(journal,state)
    try:
        result=aws.call('apigatewayv2','create-route',{'ApiId':api_id,'RouteKey':key,'Target':'integrations/'+integration,'AuthorizationType':'NONE'})
        state['steps'][key]={'status':'complete','at':aws.now(),'routeId':result['RouteId']};aws.save(journal,state)
    except Exception as exc:
        state['steps'][key].update(status='failed-review-required',error=str(exc));aws.save(journal,state);raise
after=aws.call('apigatewayv2','get-routes',{'ApiId':api_id})['Items']
http_evidence=OUT/'gateway-http.json'
if 'GET /app/' in state['steps'] and http_evidence.exists():
    verified=json.loads(http_evidence.read_text())
    if any(c['path']=='/app/' and c['status']==200 for c in verified['checks']):
        state['steps']['GET /app/'].update(status='rejected-not-created-resolved',
            resolution='Trailing slash is normalized by HTTP API; GET /app serves /app/, verified by gateway-http.json')
        aws.save(journal,state)
assert {r['RouteId']:r for r in before if r['RouteId'] in original_ids}=={r['RouteId']:r for r in after if r['RouteId'] in original_ids}
aws.save(OUT/'gateway-after.json',{'at':aws.now(),'api':api,'routes':after,'originalSevenJwtRoutesUnchanged':True,
    'integration':aws.call('apigatewayv2','get-integration',{'ApiId':api_id,'IntegrationId':integration}),
    'authorizers':aws.call('apigatewayv2','get-authorizers',{'ApiId':api_id}),
    'stages':aws.call('apigatewayv2','get-stages',{'ApiId':api_id})})
print('SPA GET paths configured; all seven JWT API routes unchanged.')
