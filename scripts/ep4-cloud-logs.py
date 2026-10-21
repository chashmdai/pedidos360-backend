"""Read only the project's token-free API access log format for the current iteration."""
import datetime as dt
import json
import aws_deploy as aws
identity=aws.call('sts','get-caller-identity');assert identity['Account']==aws.ACCOUNT and '/voclabs/' in identity['Arn']
OUT=aws.ROOT/'docs/evidence/ep4'
installation=json.loads((OUT/'installation.json').read_text())
start=int(dt.datetime.fromisoformat(installation['at']).timestamp()*1000)-120000
response=aws.call('logs','filter-log-events',{'logGroupName':'/pedidos360/api-gateway','startTime':start,'limit':500})
events=[]
for event in response['events']:
    data=json.loads(event['message'])
    events.append({'timestamp':event['timestamp'],**{k:data[k] for k in ('requestId','routeKey','status','latency') if k in data}})
report={'at':aws.now(),'source':'CloudWatch /pedidos360/api-gateway','events':events}
aws.save(OUT/'gateway-access-logs.json',report)
print(json.dumps({'events':len(events),'statuses':sorted({e['status'] for e in events}),'routes':sorted({e['routeKey'] for e in events})}))
