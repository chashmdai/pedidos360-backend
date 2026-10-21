"""Read-only local delivery checks; no AWS calls, builds or Git writes.

Run after visually reviewing the current PDF:
  python scripts/ep4-delivery-check.py --confirm-visual-review
The flag records an operator assertion, not an automated visual assessment.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote
import zipfile

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
FRONT = ROOT.parent / 'pedidos360-frontend'
EVIDENCE = ROOT / 'docs/evidence/ep4'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--confirm-visual-review', action='store_true')
args = parser.parse_args()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def load(name):
    return json.loads((EVIDENCE / name).read_text())


prior = {
    ROOT: ('https://github.com/chashmdai/pedidos360-backend.git',
           '0c8061405157bf5fb2454099ebedb89adf524547'),
    FRONT: ('https://github.com/chashmdai/pedidos360-frontend.git',
            '4c4040e1807a34e77d1a15e00758ebe25e36cc98'),
}
assert subprocess.check_output(['id', '-un'], text=True).strip() == 'codex'
for root, (remote, old) in prior.items():
    assert git(root, 'rev-parse', '--show-toplevel') == str(root)
    assert git(root, 'remote', 'get-url', 'origin') == remote
    assert git(root, 'branch', '--show-current') == 'main'
    subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor',
                    old, 'HEAD'], check=True)
    subprocess.run(['git', '-C', str(root), 'diff', '--check'], check=True)
assert not git(ROOT, 'diff', prior[ROOT][1], '--', 'docs/evidence/ep3',
               'docs/EP3_RABBITMQ_EVIDENCIAS.pdf')
assert sha(ROOT / 'docs/EP3_RABBITMQ_EVIDENCIAS.pdf') == (
    '19eb27a1fc7a1b2d1ddc72d3def66185047c8d884a268335807cdeb984211997')
assert not git(FRONT, 'diff', prior[FRONT][1], '--', '*.css', 'public')

release = load('release-manifest.json')
cloud = load('aws-final-verification.json')['output']
build = Path.home() / '.cache/pedidos360-ep4/build'
class_count = 0
for name, digest in cloud['artifacts'].items():
    module = name.removesuffix('.jar')
    jar = build / module / f'{module}-0.1.0-SNAPSHOT.jar'
    assert sha(jar) == digest == release['files'][name], module
    with zipfile.ZipFile(jar) as archive:
        for file in (build / module / 'classes').rglob('*'):
            if file.is_file():
                inside = 'BOOT-INF/classes/' + file.relative_to(
                    build / module / 'classes').as_posix()
                assert archive.read(inside) == file.read_bytes(), str(file)
                class_count += 1
for relative, digest in release['files'].items():
    if relative.endswith('.jar'):
        continue
    path = (Path.home() / '.cache/pedidos360-ep4/frontend/dist' /
            relative.removeprefix('frontend/')) if relative.startswith('frontend/') else ROOT / relative
    assert sha(path) == digest, relative
for source in (FRONT / 'src').rglob('*'):
    if source.is_file():
        assert source.read_bytes() == (Path.home() / '.cache/pedidos360-ep4/frontend' /
                                      source.relative_to(FRONT)).read_bytes(), str(source)
assert all(check['status'] == check['expected'] for check in load('gateway-http.json')['checks'])
assert load('gateway-http.json')['verifiedFrontendBytesMatchRelease']
assert all(value['status'] == 'UP' for value in cloud['health'].values())
assert all(value['allPreviousHashesUnchanged'] for value in cloud['preservation'].values())

def java_results(name):
    log = (EVIDENCE / name).read_text()
    assert '[INFO] BUILD SUCCESS' in log
    rows = re.findall(r'Tests run: (\d+), Failures: (\d+), Errors: (\d+), '
                      r'Skipped: (\d+),[^\n]* -- in ([\w.]+)', log)
    assert rows and all(int(fail) == int(error) == int(skip) == 0
                        for count, fail, error, skip, klass in rows)
    return {klass: int(count) for count, fail, error, skip, klass in rows}


clean_tests = java_results('backend-verify.txt')
http_tests = java_results('insights-http-final.txt')
assert sum(clean_tests.values()) == 39
assert sum(count for klass, count in http_tests.items() if klass not in clean_tests) == 2
assert sum((clean_tests | http_tests).values()) == 41
react_log = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '',
                   (EVIDENCE / 'frontend-tests.txt').read_text())
assert re.search(r'Tests\s+11 passed \(11\)', react_log)
assert 'built in' in (EVIDENCE / 'frontend-build.txt').read_text()

# Validate local documentation links without fetching remote URLs or sessions.
docs = [ROOT / 'README.md', FRONT / 'README.md', *sorted((ROOT / 'docs').glob('EP4*.md')),
        EVIDENCE / 'README.md']
local_links = 0
for file in docs:
    for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', file.read_text()):
        target = target.strip('<>').split('#', 1)[0]
        if not target or re.match(r'[a-zA-Z][\w+.-]*:', target):
            continue
        assert (file.parent / unquote(target)).exists(), f'{file.name}: {target}'
        local_links += 1

# Report file names only if a sensitive pattern is detected, never its value.
patterns = [re.compile(p) for p in (
    rb'(?:AKIA|ASIA)[A-Z0-9]{16}',
    rb'gh[pousr]_[A-Za-z0-9]{30,}',
    rb'github_pat_[A-Za-z0-9_]{40,}',
    rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    rb'eyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}',
)]
scanned = 0
for root in prior:
    candidates = subprocess.check_output(['git', '-C', str(root), 'ls-files',
        '--cached', '--others', '--exclude-standard', '-z']).decode().split('\0')
    for name in set(candidates):
        if not name or name == 'docs/evidence/ep3/evidencias.zip':
            continue  # pre-existing, untracked user artifact; never staged here
        file = root / name
        if not file.is_file():
            continue
        assert not re.search(r'(?:^|/)(?:node_modules|target|dist|\.secrets|\.venv)/', name), name
        assert not (file.name.startswith('.env') and file.name != '.env.example'), name
        assert file.suffix not in {'.pem', '.key', '.har', '.cnf'}, name
        data = file.read_bytes()
        assert not any(pattern.search(data) for pattern in patterns), f'Sensitive pattern: {root.name}/{name}'
        scanned += 1
for script in list((ROOT / 'scripts').glob('ep4*.py')) + list((ROOT / 'deploy').glob('ep4*.py')):
    ast.parse(script.read_text(), filename=str(script))
for script in list((ROOT / 'scripts').glob('ep4*.sh')) + [ROOT / 'docker/rabbitmq/ep4-entrypoint.sh']:
    subprocess.run(['bash', '-n', str(script)], check=True)

for capture in load('captures.json'):
    assert sha(EVIDENCE / capture['file']) == capture['sha256'], capture['file']
pdf_path = ROOT / 'docs/EP4_IMPLEMENTACION_EVIDENCIAS.pdf'
pdf = PdfReader(pdf_path)
assert len(pdf.pages) == 7
for page in pdf.pages:
    assert abs(float(page.mediabox.width) - 595.2756) < .1
    assert abs(float(page.mediabox.height) - 841.8898) < .1
    assert len(page.extract_text().strip()) > 150
    assert '\u25a0' not in page.extract_text()
assert args.confirm_visual_review, 'Render and visually inspect all pages, then explicitly confirm'
report = {
    'at': datetime.now(timezone.utc).isoformat(),
    'environment': 'WSL codex; local inspection of existing test/cloud evidence, no AWS requests',
    'pdf': {'file': pdf_path.name, 'sha256': sha(pdf_path), 'pages': len(pdf.pages),
            'format': 'A4', 'allPagesVisuallyReviewedByOperator': True,
            'visualReviewMethod': 'Poppler PNGs, all seven pages inspected; page 2 spacing corrected'},
    'javaDistinctTests': 41, 'javaCleanVerifyTests': 39, 'additionalHttpTests': 2,
    'reactTests': 11, 'productionBuildPassed': True,
    'installedRelease': release['release'],
    'sixJarsMatchNativeManifestAndAws': True,
    'compiledClassAndResourceFilesMatchJar': class_count,
    'frontendFilesMatchVerifiedBuildSources': True,
    'ep3PdfAndTrackedEvidenceUnchanged': True, 'frontendCssUnchanged': True,
    'newOrTrackedFilesScanned': scanned, 'localDocumentationLinksChecked': local_links,
    'captureHashesChecked': len(load('captures.json')),
    'sensitivePatternScan': 'passed; not a claim of exhaustive secret detection',
    'untrackedUserEp3ZipExcluded': True,
}
(EVIDENCE / 'delivery-checks.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
