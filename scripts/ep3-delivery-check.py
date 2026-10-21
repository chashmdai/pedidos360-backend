"""Check the deliverable, excluding secrets/builds; write evidence and capture index.

Does not call AWS or inspect browser sessions. Known private values are used only
for an in-memory scan; findings identify filenames, never secret values.
"""
import ast
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote
import xml.etree.ElementTree as ET
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parent.parent
FRONT=ROOT.parent/'pedidos360-frontend'
E=ROOT/'docs/evidence/ep3'
EXCLUDE={'.git','target','node_modules','dist','tmp','__pycache__','.venv','venv','test-results','playwright-report'}

def candidates(root):
    for path in root.rglob('*'):
        if not path.is_file() or any(x in EXCLUDE for x in path.relative_to(root).parts):continue
        if path.name.startswith('.env') and path.name!='.env.example':continue
        if path.suffix in ('.log','.tsbuildinfo','.pyc'):continue
        yield path

def main():
    old=E/'baseline-README.md'
    if old.exists():old.rename(E/'baseline-README.txt') # Own historical snapshot, not a current relative-link document.
    manifest=json.loads((E/'captures.json').read_text())
    for item in manifest:
        if item['file']=='20-entra-order-after-reload.png':
            item['file']='20-entra-history-preserved.png'
            item['description']='Vista real de pedidos anteriores conservados en la sesión Entra; no muestra la tarjeta del nuevo pedido'
        file=E/item['file']
        assert file.exists(),item['file']
        assert hashlib.sha256(file.read_bytes()).hexdigest()==item['sha256'],item['file']+' changed after capture'
    assert set(m['file'] for m in manifest)=={p.name for p in E.glob('*.png')}
    (E/'captures.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    lines=['# Capturas EP3 completadas','',
        'Conservo el nombre histórico de este archivo para no romper referencias. Las capturas locales y Entra ya están completadas. React está autorizado por el docente.',
        '', 'Usé Chromium/Playwright en WSL como `codex` y el navegador integrado de Codex para la sesión institucional. No capturé contraseñas, MFA, tokens ni almacenamiento de sesión.',
        '', 'Las imágenes de logs/JSON son vistas explícitas de evidencia ejecutada. No simulan una terminal ni otra interfaz. Los originales de broker/SPA se conservan; el PDF recorta detalles sin alterar esos archivos.',
        '', 'El formulario institucional está en 19; el resultado 201 y comprobante/ACK están en `entra-verification.json`, access logs y `pdf-flow.png`. La captura 20 muestra pedidos previos, no la tarjeta del nuevo pedido. La renovación 18 muestra su resultado verificado sin la identidad privada del usuario.',
        '', '| Captura real | Fuente / descripción |','|---|---|']
    for item in sorted(manifest,key=lambda m:m['file']):
        lines.append(f"| [{item['file']}]({item['file']}) | {item['description']} |")
    lines+=['','El manifiesto `captures.json` conserva URL/fuente, fecha y SHA-256. El PDF principal está en `../../EP3_RABBITMQ_EVIDENCIAS.pdf`.',
        '', '## Repetición controlada', '', 'Desde WSL `codex`, con el runtime local y broker propios iniciados:', '', '```bash',
        'python3 scripts/verify-ep3.py --restart-broker',
        '~/.local/share/pedidos360-ep3/evidence-venv/bin/python scripts/ep3-capture.py',
        '~/.local/share/pedidos360-ep3/evidence-venv/bin/python scripts/ep3-observe-delivery.py',
        '~/.local/share/pedidos360-ep3/evidence-venv/bin/python scripts/ep3-capture-details.py',
        '```', '', 'Los scripts locales agregan pedidos de prueba y detienen únicamente procesos/broker EP3 identificados. No ejecutarlos contra el perfil Entra. Su login/MFA siempre es manual. No repetir Entra mediante fixtures ni publicar archivos de sesión.',
        '', 'Para regenerar el PDF a partir de evidencia ya verificada: `python scripts/ep3-create-pdf.py` y `python scripts/ep3-pdf-qa.py`, usando el venv con `scripts/requirements-evidence.txt`. Revisar todas las páginas renderizadas antes de entregar.']
    (E/'CAPTURAS_PENDIENTES.md').write_text('\n'.join(lines)+'\n')
    private=Path.home()/'.config/pedidos360/ep3';known=[]
    for file in private.glob('*-password'):
        value=file.read_text().strip()
        if len(value)>8:known.append(value)
    for component in json.loads((private/'components.json').read_text()).values():
        known.extend(value for key,value in component.items() if 'PASSWORD' in key and len(value)>8)
    secret_findings=[];broken=[];syntax=dict(python=0,bash=0,json=0,xml=0)
    for root in (ROOT,FRONT):
        for file in candidates(root):
            try:text=file.read_text()
            except (UnicodeError,OSError):continue
            relative=str(file.relative_to(root))
            if any(value in text for value in known):secret_findings.append(dict(file=root.name+'/'+relative,kind='known_private_value'))
            for label,pattern in [('private_key',r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),('jwt',r'eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}'),('aws_access_key',r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b')]:
                if re.search(pattern,text):secret_findings.append(dict(file=root.name+'/'+relative,kind=label))
            if file.suffix=='.py':ast.parse(text,filename=str(file));syntax['python']+=1
            if file.suffix=='.sh':subprocess.run(['bash','-n',str(file)],check=True);syntax['bash']+=1
            if file.suffix=='.json':json.loads(text);syntax['json']+=1
            if file.suffix=='.xml':ET.fromstring(text);syntax['xml']+=1
            if file.suffix=='.md':
                for target in re.findall(r'\]\((<[^>]+>|[^)]+)\)',text):
                    target=unquote(target.strip('<>'))
                    if re.match(r'^[a-zA-Z]+:',target) or target.startswith('#'):continue
                    if not (file.parent/target.split('#')[0]).exists():broken.append(dict(file=root.name+'/'+relative,target=target))
    reports=list((Path.home()/'.cache/pedidos360-ep3/build').glob('*/surefire-reports/TEST-*.xml'))
    totals={key:sum(int(ET.parse(file).getroot().get(key,'0')) for file in reports) for key in ('tests','failures','errors','skipped')}
    assert totals==dict(tests=23,failures=0,errors=0,skipped=0)
    css=hashlib.sha256((FRONT/'src/style.css').read_bytes()).hexdigest()
    assert css=='ad493558ad25d8e428fcb7732646307727c8bceb358118688cf2b08a4bce24cc'
    assert 'BUILD SUCCESS' in (E/'backend-verify.txt').read_text()
    assert re.search(r'Tests\s+10 passed',re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',(E/'frontend-tests.txt').read_text()))
    local=json.loads((E/'runtime-verification.json').read_text())
    assert local['complete'] and local['passed']==15 and len(local['httpTrace'])==48
    assert all(r['expected']==r['actual'] for r in local['httpTrace'])
    entra=json.loads((E/'entra-verification.json').read_text())
    assert entra['mode']=='MICROSOFT_ENTRA_REAL' and entra['receipt']['total']==30970
    close=json.loads((E/'entra-browser-close.json').read_text())
    assert close['microsoftLogoutObserved'] and close['logoutButtons']==0 and close['finalUrl']=='http://localhost:5173/'
    pdf=ROOT/'docs/EP3_RABBITMQ_EVIDENCIAS.pdf';reader=PdfReader(pdf)
    assert len(reader.pages)==8
    pdf_text='\n'.join(page.extract_text() for page in reader.pages)
    assert all(value not in pdf_text for value in known)
    before=[json.loads(line) for line in (E/'containers-before.jsonl').read_text().splitlines() if line]
    after=[json.loads(line) for line in subprocess.check_output(['docker','ps','-a','--format','{{json .}}'],text=True).splitlines()]
    after_by_id={r['ID']:r for r in after}
    assert all(r['ID'] in after_by_id and after_by_id[r['ID']]['State']==r['State'] for r in before)
    # Public preservation proof needs no unrelated project names, mounts or labels.
    preservation=[dict(idSha256=hashlib.sha256(r['ID'].encode()).hexdigest(),stateBefore=r['State'],stateAfter=after_by_id[r['ID']]['State']) for r in before]
    (E/'container-preservation-final.json').write_text(json.dumps(dict(allPreserved=True,containers=preservation),indent=2)+'\n')
    sources={}
    for root in (ROOT,FRONT):
        for file in candidates(root):
            relative=file.relative_to(root)
            if 'docs' in relative.parts:continue
            sources[root.name+'/'+str(relative)]=hashlib.sha256(file.read_bytes()).hexdigest()
    source_hash=hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest()
    (E/'verified-source-files.json').write_text(json.dumps(dict(treeSha256=source_hash,files=sources),indent=2)+'\n')
    quality=dict(at=datetime.now(timezone.utc).isoformat(),surefire=totals,frontendTests=10,buildsPassed=True,
        localAcceptanceGroups=15,localHttpAssertions=48,entraReal=True,entraHttp=entra['http'],
        logoutAndRouteProtection=True,reactAuthorizedByTeacher=True,captures=len(manifest),
        pdfPages=8,pdfSha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),sourceTreeSha256=source_hash,
        frontendStylesSha256=css,preexistingContainersUnchanged=True,syntax=syntax,
        secretScanFindings=secret_findings,brokenReportLinks=broken,pendingRequired=[],
        limits=['No real Admin Entra 200 claimed; User 403 is verified','No HA, natural token expiration or EP3 AWS test claimed','Two preexisting high npm dependency advisories remain documented'])
    (E/'quality-final.json').write_text(json.dumps(quality,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(quality,indent=2,ensure_ascii=False))
    assert not secret_findings and not broken,'Resolve listed findings before publication'

if __name__=='__main__':main()
