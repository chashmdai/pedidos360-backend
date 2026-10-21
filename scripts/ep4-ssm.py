"""Execute an explicit, reviewed script only on the reconciled project instance."""
import argparse
import base64
import json
from pathlib import Path
import time
import aws_deploy as aws

parser=argparse.ArgumentParser()
parser.add_argument('script',type=Path)
parser.add_argument('--output',default='instance-inspection.json')
parser.add_argument('--argument',action='append',default=[])
args=parser.parse_args()
assert args.script.is_file()
aws.PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700)
identity=aws.call('sts','get-caller-identity')
assert identity['Account']==aws.ACCOUNT and '/voclabs/' in identity['Arn']
state=json.loads(aws.JOURNAL.read_text())
instance=state['steps']['ec2']['response']['Instances'][0]['InstanceId']
actual=aws.call('ec2','describe-instances',{'InstanceIds':[instance]})['Reservations'][0]['Instances'][0]
assert actual['State']['Name']=='running' and {'Key':'Project','Value':'Pedidos360'} in actual['Tags']
script=base64.b64encode(args.script.read_bytes()).decode()
arguments=base64.b64encode(json.dumps([str(args.script),*args.argument]).encode()).decode()
command="python3 -c \"import base64,sys,json; sys.argv=json.loads(base64.b64decode('"+arguments+"')); exec(compile(base64.b64decode('"+script+"'),'<pedidos360-ep4>','exec'))\""
result=aws.call('ssm','send-command',{'InstanceIds':[instance],'DocumentName':'AWS-RunShellScript',
 'Comment':'Pedidos360 EP4 explicit project script','TimeoutSeconds':600,
 'Parameters':{'commands':[command],'executionTimeout':['600']}})
command_id=result['Command']['CommandId']
print('SSM command '+command_id,flush=True)
destination=aws.ROOT/'docs/evidence/ep4'/args.output
assert destination.parent==aws.ROOT/'docs/evidence/ep4'
while True:
    time.sleep(3)
    try: invocation=aws.call('ssm','get-command-invocation',{'CommandId':command_id,'InstanceId':instance})
    except RuntimeError as exc:
        if 'InvocationDoesNotExist' in str(exc): continue
        raise
    if invocation['Status'] in ('Pending','InProgress','Delayed'): continue
    stdout=invocation.get('StandardOutputContent','')
    try: output=json.loads(stdout)
    except ValueError: output=stdout
    report={'at':aws.now(),'instanceId':instance,'commandId':command_id,'status':invocation['Status'],
            'exitCode':invocation['ResponseCode'],'output':output,'error':invocation.get('StandardErrorContent','')}
    aws.save(destination,report)
    print(json.dumps(report,indent=2))
    assert invocation['Status']=='Success', 'Remote script failed; inspect evidence before retry'
    break
