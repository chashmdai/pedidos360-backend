"""Execute an explicit, reviewed script only on the reconciled project instance (evidence saved under aws.EVIDENCE)."""
import argparse
import json
from pathlib import Path
import aws_deploy as aws
import ssm_remote

parser=argparse.ArgumentParser()
parser.add_argument('script',type=Path)
parser.add_argument('--output',default='instance-inspection.json')
parser.add_argument('--argument',action='append',default=[])
args=parser.parse_args()
assert args.script.is_file()
aws.PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700);aws.EVIDENCE.mkdir(parents=True,exist_ok=True)
# Evidence of the current deployment target (config/aws-target.json; EP5: docs/evidence/ep5/aws).
destination=aws.EVIDENCE/args.output
assert destination.parent==aws.EVIDENCE and '/' not in args.output
instance=ssm_remote.verify_target()
command_id,invocation=ssm_remote.run(args.script,args.argument,instance,on_sent=lambda c:print('SSM command '+c,flush=True))
stdout=invocation.get('StandardOutputContent','')
try: output=json.loads(stdout)
except ValueError: output=stdout
report={'at':aws.now(),'instanceId':instance,'commandId':command_id,'status':invocation['Status'],
        'exitCode':invocation['ResponseCode'],'output':output,'error':invocation.get('StandardErrorContent','')}
aws.save(destination,report)
print(json.dumps(report,indent=2))
assert invocation['Status']=='Success', 'Remote script failed; inspect evidence before retry'
