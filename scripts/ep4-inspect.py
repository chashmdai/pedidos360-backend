"""Read-only EP4 inventory. Preserve every historical EP3/phase5 evidence file."""
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import aws_deploy as aws

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'docs/evidence/ep4'
OUT.mkdir(parents=True, exist_ok=True)
aws.PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
aws.state = json.loads(aws.JOURNAL.read_text())
r = aws.response
identity = aws.call('sts', 'get-caller-identity')
assert identity['Account'] == aws.ACCOUNT
assert identity['Arn'].startswith(f'arn:aws:sts::{aws.ACCOUNT}:assumed-role/voclabs/')
instance = r('ec2')['Instances'][0]['InstanceId']
requests = [
 ('vpcs','ec2','describe-vpcs',{}),
 ('subnets','ec2','describe-subnets',{'Filters':[{'Name':'vpc-id','Values':[r('vpc')['Vpc']['VpcId']]}]}),
 ('security-groups','ec2','describe-security-groups',{}),
 ('route-tables','ec2','describe-route-tables',{}),
 ('internet-gateway','ec2','describe-internet-gateways',{'InternetGatewayIds':[r('igw')['InternetGateway']['InternetGatewayId']]}),
 ('instances','ec2','describe-instances',{}),
 ('volumes','ec2','describe-volumes',{'Filters':[{'Name':'attachment.instance-id','Values':[instance]}]}),
 ('rds','rds','describe-db-instances',{}),
 ('alb','elbv2','describe-load-balancers',{}),
 ('target-groups','elbv2','describe-target-groups',{}),
 ('listeners','elbv2','describe-listeners',{'LoadBalancerArn':r('alb')['LoadBalancers'][0]['LoadBalancerArn']}),
 ('targets','elbv2','describe-target-health',{'TargetGroupArn':r('target-group')['TargetGroups'][0]['TargetGroupArn']}),
 ('vpc-links','apigatewayv2','get-vpc-links',{}),
 ('apis','apigatewayv2','get-apis',{}),
 ('api','apigatewayv2','get-api',{'ApiId':r('http-api')['ApiId']}),
 ('routes','apigatewayv2','get-routes',{'ApiId':r('http-api')['ApiId']}),
 ('integrations','apigatewayv2','get-integrations',{'ApiId':r('http-api')['ApiId']}),
 ('authorizers','apigatewayv2','get-authorizers',{'ApiId':r('http-api')['ApiId']}),
 ('stages','apigatewayv2','get-stages',{'ApiId':r('http-api')['ApiId']}),
 ('ssm','ssm','describe-instance-information',{'Filters':[{'Key':'InstanceIds','Values':[instance]}]}),
 ('logs','logs','describe-log-groups',{'logGroupNamePrefix':'/pedidos360/'}),
]
report = {'at':dt.datetime.now(dt.timezone.utc).isoformat(),'account':identity['Account'],
          'role':'voclabs','region':aws.REGION,'mode':'read-only','resources':{},'errors':{}}
def inspect(item):
    name, service, operation, payload = item
    try: return name, aws.call(service,operation,payload), None
    except Exception as exc: return name, None, str(exc)
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    for name, response, error in pool.map(inspect, requests):
        if error: report['errors'][name] = error
        else: report['resources'][name] = response
        print(name + (': ERROR '+error if error else ': inspected'), flush=True)
aws.save(OUT/'aws-inventory.json',report)
assert not report['errors'], 'Inventory failed; inspect exact errors before any write'
resources = report['resources']
actual = [i for b in resources['instances']['Reservations'] for i in b['Instances'] if i['InstanceId']==instance]
assert len(actual)==1 and any(t=={'Key':'Project','Value':'Pedidos360'} for t in actual[0].get('Tags',[]))
assert any(v['VpcId']==r('vpc')['Vpc']['VpcId'] for v in resources['vpcs']['Vpcs'])
original_routes={r('route-'+str(i))['RouteId'] for i in range(7)}
ep4_journal=OUT/'gateway-journal.json'
ep4_routes={v['routeId'] for v in json.loads(ep4_journal.read_text())['steps'].values() if 'routeId' in v} if ep4_journal.exists() else set()
assert {x['RouteId'] for x in resources['routes']['Items']} == original_routes | ep4_routes
initial=OUT/'aws-inventory-before.json'
preservation={}
def unordered(value):
    if isinstance(value,dict):return {k:unordered(v) for k,v in value.items()}
    if isinstance(value,list):return sorted((unordered(v) for v in value),key=lambda v:json.dumps(v,sort_keys=True))
    return value
if initial.exists():
    old=json.loads(initial.read_text())['resources']
    for name,collection,key,fields in [('security-groups','SecurityGroups','GroupId',('IpPermissions','IpPermissionsEgress')),('route-tables','RouteTables','RouteTableId',('Routes','Associations'))]:
        before={item[key]:{field:item[field] for field in fields} for item in old[name][collection]}
        after={item[key]:{field:item[field] for field in fields} for item in resources[name][collection]}
        assert all(unordered(after.get(k))==unordered(v) for k,v in before.items()),'Existing network rule drift: '+name
        preservation[name]={'previousResources':len(before),'allPreviousRulesUnchanged':True}
summary = {'instanceId':instance,'instanceState':actual[0]['State']['Name'],
 'instanceType':actual[0]['InstanceType'],'ssm':[{'id':i['InstanceId'],'status':i['PingStatus']} for i in resources['ssm']['InstanceInformationList']],
 'rds':[{'id':d['DBInstanceIdentifier'],'status':d['DBInstanceStatus'],'class':d['DBInstanceClass']} for d in resources['rds']['DBInstances']],
 'targets':resources['targets']['TargetHealthDescriptions'], 'sevenRecordedRoutesMatch':True,
 'networkPreservation':preservation,
 'ep3PdfSha256':hashlib.sha256((ROOT/'docs/EP3_RABBITMQ_EVIDENCIAS.pdf').read_bytes()).hexdigest()}
aws.save(OUT/'reconciliation.json',summary)
print(json.dumps(summary,indent=2))
