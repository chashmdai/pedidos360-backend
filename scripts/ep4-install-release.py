"""Verify the uploaded archive before unpacking and running its reviewed installer via SSM."""
import json
from pathlib import Path
import subprocess
import sys
import aws_deploy as aws

manifest=json.loads((aws.ROOT/'docs/evidence/ep4/release-manifest.json').read_text())
release=manifest['release'];assert release.startswith('ep4-') and release.replace('-','').isalnum()
archive='pedidos360-'+release+'.tgz'
state=Path.home()/'.local/state/pedidos360-ep4';state.mkdir(parents=True,exist_ok=True,mode=0o700)
script=state/'install-current.py'
script.write_text('''import hashlib,json,subprocess,tarfile
from pathlib import Path
root=Path('/home/ubuntu/pedidos360-ep4-stage')
archive=root/'''+repr(archive)+'''
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='''+repr(manifest['archiveSha256'])+'''
with tarfile.open(archive) as tar:
    for member in tar.getmembers():
        assert (root/member.name).resolve().is_relative_to(root/'''+repr(release)+'''), 'Unsafe archive member'
    tar.extractall(root,filter='data')
subprocess.run(['python3',str(root/'''+repr(release)+'''/'deploy/ep4-install.py'),str(root/'''+repr(release)+''')],check=True)
''')
subprocess.run([sys.executable,str(aws.ROOT/'scripts/ep4-ssm.py'),str(script),'--output','installation.json'],check=True)
