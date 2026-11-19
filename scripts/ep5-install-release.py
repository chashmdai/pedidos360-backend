"""Run the reviewed EP5 installer on the reconciled EC2 through SSM. Verifies the uploaded archive's SHA-256
before unpacking (no path traversal) and removes the uploaded archive (it carries the private secrets file)
only after a successful installation."""
import json
from pathlib import Path
import subprocess
import sys
import aws_deploy as aws

manifest = json.loads((aws.EVIDENCE / "release-manifest.json").read_text())
release = manifest["release"]
assert release.startswith("ep5-") and release.replace("-", "").isalnum()
archive = f"pedidos360-{release}.tgz"
state = Path.home() / ".local/state/pedidos360-ep5"; state.mkdir(parents=True, exist_ok=True, mode=0o700)
script = state / "install-current.py"
script.write_text(f"""import hashlib,subprocess,tarfile
from pathlib import Path
root=Path('/home/ubuntu/pedidos360-ep5-stage')
archive=root/{archive!r}
assert hashlib.sha256(archive.read_bytes()).hexdigest()=={manifest['archiveSha256']!r}, 'Archive checksum mismatch'
with tarfile.open(archive) as tar:
    for member in tar.getmembers():
        assert (root/member.name).resolve().is_relative_to(root/{release!r}), 'Unsafe archive member'
    tar.extractall(root,filter='data')
subprocess.run(['python3',str(root/{release!r}/'deploy/ep5-install.py'),str(root/{release!r})],check=True)
archive.unlink()
print('ARCHIVE_REMOVED')
""")
subprocess.run([sys.executable, str(aws.ROOT / "scripts/ep4-ssm.py"), str(script), "--output", "installation.json"], check=True)
