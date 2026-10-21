"""Read-only reconciliation of recorded IDs. Never creates/retries/removes a resource."""
import json
import aws_deploy as a

a.PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
a.state = json.loads(a.JOURNAL.read_text())
identity = a.call('sts','get-caller-identity')
assert identity['Account'] == a.ACCOUNT and identity['Arn'].startswith(f'arn:aws:sts::{a.ACCOUNT}:assumed-role/voclabs/')
r = a.response
requests = [
    ('vpc','ec2','describe-vpcs',{'VpcIds':[r('vpc')['Vpc']['VpcId']]}),
    ('subnets','ec2','describe-subnets',{'SubnetIds':[r(n)['Subnet']['SubnetId'] for n in ('public-b','private-b','private-c')]}),
    ('igw','ec2','describe-internet-gateways',{'InternetGatewayIds':[r('igw')['InternetGateway']['InternetGatewayId']]}),
    ('route-tables','ec2','describe-route-tables',{'RouteTableIds':[r(n)['RouteTable']['RouteTableId'] for n in ('public-rt','private-rt')]}),
    ('security-groups','ec2','describe-security-groups',{'GroupIds':[r(n+'-sg')['GroupId'] for n in ('vpclink','alb','app','db')]}),
    ('ec2','ec2','describe-instances',{'InstanceIds':[r('ec2')['Instances'][0]['InstanceId']]}),
    ('key','ec2','describe-key-pairs',{'KeyNames':['pedidos360-deploy']}),
    ('rds','rds','describe-db-instances',{'DBInstanceIdentifier':'pedidos360-mysql'}),
    ('db-subnets','rds','describe-db-subnet-groups',{'DBSubnetGroupName':'pedidos360-db-subnets'}),
    ('db-parameters','rds','describe-db-parameters',{'DBParameterGroupName':'pedidos360-mysql84','Source':'user'}),
    ('alb','elbv2','describe-load-balancers',{'LoadBalancerArns':[r('alb')['LoadBalancers'][0]['LoadBalancerArn']]}),
    ('target-group','elbv2','describe-target-groups',{'TargetGroupArns':[r('target-group')['TargetGroups'][0]['TargetGroupArn']]}),
    ('listener','elbv2','describe-listeners',{'ListenerArns':[r('listener')['Listeners'][0]['ListenerArn']]}),
    ('vpclink','apigatewayv2','get-vpc-link',{'VpcLinkId':r('vpclink')['VpcLinkId']}),
    ('api','apigatewayv2','get-api',{'ApiId':r('http-api')['ApiId']}),
    ('authorizer','apigatewayv2','get-authorizer',{'ApiId':r('http-api')['ApiId'],'AuthorizerId':r('jwt-authorizer')['AuthorizerId']}),
    ('integration','apigatewayv2','get-integration',{'ApiId':r('http-api')['ApiId'],'IntegrationId':r('integration')['IntegrationId']}),
    ('routes','apigatewayv2','get-routes',{'ApiId':r('http-api')['ApiId']}),
    ('stage','apigatewayv2','get-stage',{'ApiId':r('http-api')['ApiId'],'StageName':'$default'}),
    ('logs','logs','describe-log-groups',{'logGroupNamePrefix':'/pedidos360/api-gateway'}),
    ('foreign-default-sg','ec2','describe-security-groups',{'GroupIds':['sg-0c05d09127edbca62']}),
    ('foreign-default-routes','ec2','describe-route-tables',{'RouteTableIds':['rtb-008a0df04df9688a0']}),
]
report = {'at':a.now(),'identity':identity,'resources':{},'errors':{}}
destination = a.EVIDENCE / ('reconciliation-'+a.now()[:19].replace(':','')+'.json')
for name, service, operation, payload in requests:
    try:
        report['resources'][name] = a.call(service,operation,payload)
        print(name+': recorded resource found',flush=True)
    except RuntimeError as exc:
        report['errors'][name] = str(exc)
        print(name+': inspection failed; recorded exact error',flush=True)
    a.save(destination,report)
if report['errors']:
    raise SystemExit('Reconciliation contains errors: inspect before any write')
# Compare explicit shared rules with the pre-creation inventory, not only their existence.
baseline = a.ROOT/'docs/evidence/phase4/inventory/us-east-1'
old_sg = json.loads((baseline/'security-groups.json').read_text(encoding='utf-8-sig'))['response'][0]
sg = report['resources']['foreign-default-sg']['SecurityGroups'][0]
old_rt = json.loads((baseline/'route-tables.json').read_text(encoding='utf-8-sig'))['response'][0]
rt = report['resources']['foreign-default-routes']['RouteTables'][0]
report['defaultRulesUnchanged'] = sg['IpPermissions'] == old_sg['Ingress'] and sg['IpPermissionsEgress'] == old_sg['Egress'] and rt['Routes'] == old_rt['Routes'] and rt['Associations'] == old_rt['Associations']
expected_routes = {r('route-'+str(i))['RouteId'] for i in range(7)}
actual_routes = {item['RouteId'] for item in report['resources']['routes']['Items']}
report['sameSevenRouteIds'] = expected_routes == actual_routes
a.save(destination,report)
assert report['defaultRulesUnchanged'], 'Default resource drift detected; do not modify it'
assert report['sameSevenRouteIds'], 'Route IDs differ from the journal'
print('All recorded IDs reconciled; default SG and route rules unchanged; seven route IDs match.')
