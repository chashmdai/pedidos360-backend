"""Package only verified artifacts and reviewed deployment files; no secrets or identity fixture."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import tarfile

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'docs/evidence/ep4'
assert '[INFO] BUILD SUCCESS' in (OUT/'backend-verify.txt').read_text()
assert 'built in' in (OUT/'frontend-build.txt').read_text()
release='ep4-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
stage=Path.home()/'.cache/pedidos360-ep4/releases'/release
stage.mkdir(parents=True,exist_ok=False)
modules=('catalog-service','orders-service','bff','receipts-service','rabbit-admin-service','order-insights-service')
for module in modules:
    shutil.copyfile(Path.home()/'.cache/pedidos360-ep4/build'/module/(module+'-0.1.0-SNAPSHOT.jar'),stage/(module+'.jar'))
shutil.copytree(Path.home()/'.cache/pedidos360-ep4/frontend/dist',stage/'frontend')
for relative in ('compose.ep4.yaml','docker/rabbitmq/ep4-entrypoint.sh','docker/rabbitmq/ep4.conf',
                 'scripts/ep4-broker.py','deploy/ep4-install.py','messaging-support/src/main/resources/pedidos-rabbit.properties'):
    target=stage/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/relative,target)
files={str(p.relative_to(stage)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(stage.rglob('*')) if p.is_file()}
manifest={'release':release,'at':dt.datetime.now(dt.timezone.utc).isoformat(),'files':files,
          'entra':json.loads((ROOT/'config/entra-public.json').read_text()),'gateway':json.loads((ROOT/'config/aws-public.json').read_text())}
(stage/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
archive=stage.parent/('pedidos360-'+release+'.tgz')
with tarfile.open(archive,'w:gz',compresslevel=1) as tar:tar.add(stage,arcname=release)
manifest.update(archiveSha256=hashlib.sha256(archive.read_bytes()).hexdigest(),archiveBytes=archive.stat().st_size)
(OUT/'release-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(Path.home()/'.local/state/pedidos360-ep4/current-bundle').write_text(str(archive))
print(str(archive))
