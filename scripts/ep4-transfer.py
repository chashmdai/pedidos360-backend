"""Transfer through SSM -> loopback SSH, with host-key pinning and a project-only key."""
import argparse
import json
import os
from pathlib import Path
import socket
import signal
import subprocess
import sys
import time
import aws_deploy as aws

ROOT=aws.ROOT
PRIVATE=Path.home()/'.config/pedidos360/ep4'
STATE=Path.home()/'.local/state/pedidos360-ep4'
STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
HOST_KEY=STATE/'known_hosts'
PORT=22224
parser=argparse.ArgumentParser();parser.add_argument('action',choices=['setup','tunnel','reset-tunnel','upload']);parser.add_argument('bundle',nargs='?',type=Path);args=parser.parse_args()
identity=aws.call('sts','get-caller-identity');assert identity['Account']==aws.ACCOUNT and '/voclabs/' in identity['Arn']
instance=json.loads(aws.JOURNAL.read_text())['steps']['ec2']['response']['Instances'][0]['InstanceId']
if args.action=='setup':
    public=(PRIVATE/'deploy-key.pub').read_text().strip()
    assert public.startswith('ssh-ed25519 ') and public.endswith(' pedidos360-ep4-ssm')
    script=STATE/'enable-transfer.py'
    script.write_text('''import json,os,pwd
from pathlib import Path
assert Path('/var/lib/pedidos360-provision/bootstrap-complete').is_file()
user=pwd.getpwnam('ubuntu')
directory=Path(user.pw_dir)/'.ssh'
directory.mkdir(exist_ok=True,mode=0o700)
file=directory/'authorized_keys'
key='''+repr('restrict,port-forwarding,permitopen="127.0.0.1:15674",permitopen="127.0.0.1:8183",permitopen="127.0.0.1:8184",permitopen="127.0.0.1:8185",permitopen="127.0.0.1:8090",permitopen="127.0.0.1:8187" '+public)+'''
old=file.read_text() if file.exists() else ''
added=key not in old.splitlines()
if added:
    with file.open('a') as output: output.write(('\\n' if old and not old.endswith('\\n') else '')+key+'\\n')
    os.chown(file,user.pw_uid,user.pw_gid)
    file.chmod(0o600)
os.chown(directory,user.pw_uid,user.pw_gid)
print(json.dumps({'hostKey':Path('/etc/ssh/ssh_host_ed25519_key.pub').read_text().strip(),'ownTransferKeyAdded':added,'publicSshIngressAdded':False}))
''')
    subprocess.run([sys.executable,str(ROOT/'scripts/ep4-ssm.py'),str(script),'--output','transfer-setup.json'],check=True)
    result=json.loads((aws.EVIDENCE/'transfer-setup.json').read_text())['output']
    key=result['hostKey'].split()
    HOST_KEY.write_text(f'[127.0.0.1]:{PORT} '+key[0]+' '+key[1]+'\n');HOST_KEY.chmod(0o600)
elif args.action=='reset-tunnel':
    pid=int((STATE/'ssm-tunnel.pid').read_text())
    process=Path('/proc')/str(pid)
    if process.exists():
        command=(process/'cmdline').read_bytes().split(b'\0')
        assert process.stat().st_uid==os.getuid() and os.getpgid(pid)==pid
        assert b'start-session' in command and instance.encode() in command and command[0].decode()==aws.CLI
        os.killpg(pid,signal.SIGTERM)
    print('Stopped only the registered local EP4 SSM tunnel; no AWS resource modified')
elif args.action=='tunnel':
    try:
        with socket.create_connection(('127.0.0.1',PORT),timeout=1): raise SystemExit('Local port already occupied; inspect the registered tunnel, do not duplicate it')
    except ConnectionRefusedError:pass
    logfile=(STATE/'ssm-tunnel.log').open('a')
    command=[aws.CLI,'ssm','start-session','--region',aws.REGION,'--target',instance,'--document-name','AWS-StartPortForwardingSession',
        '--parameters',json.dumps({'portNumber':['22'],'localPortNumber':[str(PORT)]})]
    process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=logfile,stderr=subprocess.STDOUT,start_new_session=True)
    (STATE/'ssm-tunnel.pid').write_text(str(process.pid))
    for _ in range(30):
        if process.poll() is not None:raise SystemExit('SSM tunnel failed: '+(STATE/'ssm-tunnel.log').read_text())
        try:
            with socket.create_connection(('127.0.0.1',PORT),timeout=1):print('SSM tunnel ready on loopback only');break
        except OSError:time.sleep(1)
    else:raise SystemExit('Tunnel did not become ready; inspect before retry')
elif args.action=='upload':
    assert args.bundle and args.bundle.is_file() and args.bundle.suffix=='.tgz'
    stage={'pedidos360-ep4-':'/home/ubuntu/pedidos360-ep4-stage','pedidos360-ep5-':'/home/ubuntu/pedidos360-ep5-stage'}[args.bundle.name[:15]]
    options=['-i',str(PRIVATE/'deploy-key'),'-o','UserKnownHostsFile='+str(HOST_KEY),'-o','StrictHostKeyChecking=yes','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=15','-o','ServerAliveInterval=10','-o','ServerAliveCountMax=3']
    subprocess.run(['ssh','-p',str(PORT),*options,'ubuntu@127.0.0.1','install -d -m 0700 '+stage],check=True)
    subprocess.run(['scp','-P',str(PORT),*options,str(args.bundle),'ubuntu@127.0.0.1:'+stage+'/'],check=True)
    print('Uploaded '+args.bundle.name+' over SSM; no public SSH rule added')
