"""Readable screenshots of verified data for the short PDF. No simulated console."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import threading
from http.server import ThreadingHTTPServer
import xml.etree.ElementTree as ET
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent.parent
E=ROOT/'docs/evidence/ep3'
def load(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
view=load('final_view','ep3-capture.py')
runtime=load('final_runtime','ep3-runtime.py')

def add(key,title,source,text):
    view.evidence_page(key,title,source,text)
    view.PAGES[key]=view.PAGES[key].replace(b'margin:30px;font:16px',b'margin:24px;font:18px').replace(b'font:15px/1.5 monospace',b'font:19px/1.45 monospace')

# Reconstruct only facts supported by the original workspace commit.
git=['git','-c','safe.directory='+str(ROOT.parent),'-C',str(ROOT.parent)]
try:
    commit=subprocess.check_output(git+['rev-parse','HEAD'],text=True).strip()
    pom=subprocess.check_output(git+['show','HEAD:pedidos360-backend/pom.xml'],text=True)
    modules=[e.text for e in ET.fromstring(pom).findall('{*}modules/{*}module')]
    before=dict(commit=commit,backendModules=modules,source='original workspace Git commit before EP3; saved before repository separation')
    (E/'baseline-before-ep3.json').write_text(json.dumps(before,indent=2)+'\n')
    for original,name in [('pom.xml','baseline-pom.xml'),('README.md','baseline-README.txt'),
        ('orders-service/src/main/java/cl/duoc/pedidos360/orders/infrastructure/persistence/OrderPersistence.java','baseline-OrderPersistence.java.txt')]:
        content=subprocess.check_output(git+['show','HEAD:pedidos360-backend/'+original])
        (E/name).write_bytes(content)
except subprocess.CalledProcessError:
    # On later repetitions use the previously captured baseline, not a new claim.
    before=json.loads((E/'baseline-before-ep3.json').read_text())

reports=list((Path.home()/'.cache/pedidos360-ep3/build').glob('*/surefire-reports/TEST-*.xml'))
tests=[]
for file in sorted(reports):
    report=ET.parse(file).getroot()
    tests.append({k:int(report.get(k,'0')) for k in ('tests','failures','errors','skipped')})
totals={k:sum(r[k] for r in tests) for k in ('tests','failures','errors','skipped')}
assert totals==dict(tests=23,failures=0,errors=0,skipped=0)
java='Surefire XML: '+json.dumps(totals)+'\n\n'
for file in sorted(reports):
    report=ET.parse(file).getroot()
    java+=report.get('name').split('.')[-1]+': '+report.get('tests')+' tests; failures='+report.get('failures')+', errors='+report.get('errors')+'\n'
java+='\n'+'\n'.join((E/'backend-verify.txt').read_text().splitlines()[-7:])
add('java','Java · verificación final','Surefire XML + backend-verify.txt; resumen calculado, no consola simulada',java)
react=view.ANSI.sub('',(E/'frontend-tests.txt').read_text())
react='\n'.join(line for line in react.splitlines() if any(s in line for s in ('src/','Test Files','Tests ','Duration')))
react+='\n\n'+'\n'.join(line for line in view.ANSI.sub('',(E/'frontend-build.txt').read_text()).splitlines() if any(s in line for s in ('tsc','vite','dist/','built in')))
add('react','React · tests y build finales','frontend-tests.txt + frontend-build.txt; extractos reales',react)
top={key:runtime.broker_request('GET',key+'/pedidos360-ep3') for key in ('queues','exchanges','bindings')}
toptext='RabbitMQ '+runtime.broker_request('GET','overview')['rabbitmq_version']+' · vhost pedidos360-ep3\n\n'
for q in top['queues']:
    toptext+=f"QUEUE {q['name']}\n  durable={q['durable']}; Ready={q['messages_ready']}; Unacked={q['messages_unacknowledged']}\n"
for b in top['bindings']:
    if b['source'].startswith('pedidos360.'):
        toptext+=f"\nEXCHANGE {b['source']}\n  key={b['routing_key']}\n  QUEUE {b['destination']}\n"
(E/'final-topology.json').write_text(json.dumps(top,indent=2)+'\n')
add('topology','RabbitMQ · recursos reales','GET Management API queues/exchanges/bindings; final-topology.json',toptext)
entra=json.loads((E/'entra-verification.json').read_text())
flow='MODO: MICROSOFT ENTRA REAL\n\n'+json.dumps({**entra['order'],'total':entra['receipt']['total'],'currency':entra['receipt']['currency'],'itemCount':entra['receipt']['itemCount']},indent=2)
flow+='\n\n'+ '\n'.join(re.sub(r'^.*?(?=(?:ACK |PUBLISH_CONFIRMED ))','',line) for lines in entra['publisherAndConsumerLogs'].values() for line in lines)
add('flow','Entra → pedido → evento → comprobante','entra-verification.json + logs correlacionados; sin tokens ni identidad personal',flow)
claims=json.loads((E/'entra-validated-claims.json').read_text())
security='ROL: '+claims['role']+'\nSCOPES: '+claims['Permisos de la API']+'\nTOKEN v'+claims['Versión de token']+'\nAUDIENCE: '+claims['API destinataria (audience)']+'\n\n'
access=(E/'entra-bff-http.txt').read_text().splitlines()
security+='\n'.join(next(line for line in reversed(access) if pattern in line) for pattern in
    ('GET /api/v1/me 200 ','GET /api/v1/productos 200 ','POST /api/v1/pedidos 201 ','GET /api/v1/pedidos 200 ','GET /api/v1/admin/pedidos 403 '))
add('security','Entra · permisos y respuestas HTTP','Claims públicos mostrados por /me + access log BFF; sin cabeceras ni sesiones',security)
add('renewal','Entra · renovación MSAL aceptada','entra-verification.json.tokenRefresh + entra-bff-http.txt; vista de resultados reales sin datos personales',
    entra['tokenRefresh']+'\n\n'+next(line for line in reversed(access) if 'GET /api/v1/me 200 ' in line))
logs=(E/'receipts-service.txt').read_text().splitlines()
chosen=[]
for reason in ('result=RECEIPT_STORED','result=DUPLICATE','reason=STORAGE_UNAVAILABLE','reason=RETRY_EXHAUSTED','reason=INVALID_CONTRACT','reason=PERMANENT_PROCESSING_ERROR'):
    chosen.append(next(re.sub(r'^.*?(?=(?:ACK |RETRY |NACK_DLQ ))','',line) for line in logs if reason in line))
add('errors','ACK, reintentos y NACK · ejecución local','receipts-service.txt; seis líneas reales, prefijo de logger omitido', '\n\n'.join(chosen))
messages=json.loads((E/'dlq-message-detail.json').read_text())
m=messages[0]
dlq=dict(queue='pedidos360.receipts.failed.v1',exchange=m['exchange'],routing_key=m['routing_key'],message_id=m['properties']['message_id'],headers={'x-death':m['properties']['headers']['x-death']},payload=m['payload'])
add('dlq','DLQ · rechazo real del consumidor','dlq-message-detail.json; campos de la respuesta HTTP conservada con requeue',json.dumps(dlq,indent=2,ensure_ascii=False))
local=json.loads((E/'runtime-verification.json').read_text())
http=local['httpTrace'];selected=[]
for status in (201,200,204,400,403,404,409,503):
    selected.append(next(r for r in http if r['port']==19184 and r['actual']==status and r['path'].startswith('/api/v1/rabbit/')))
admin='MODO LOCAL CON JWT FIRMADO; no prueba Admin real Entra\n\n'
for r in selected:admin+=f"HTTP {r['actual']} | {r['method']} {r['path']} (esperado {r['expected']})\n"
add('admin','Administrador REST · códigos verificados','runtime-verification.json; selección de ocho respuestas reales',admin)
recovery='MODO LOCAL; broker y volumen propios\n\n'
for check in local['checks']:
    if check['name'].startswith(('T13','T12 all')):recovery+='PASS '+check['name']+'\n'+json.dumps({k:v for k,v in check.items() if k not in ('name','status')})+'\n\n'
recovery+='\n'+(E/'controlled-broker-restart.txt').read_text()
add('recovery','Caída y recuperación de RabbitMQ','runtime-verification.json + controlled-broker-restart.txt',recovery)

server=ThreadingHTTPServer(('127.0.0.1',19190),view.Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
try:
    manifest=json.loads((E/'captures.json').read_text())
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={'width':1000,'height':750},device_scale_factor=1.5)
        for key in ('java','react','topology','flow','security','renewal','errors','dlq','admin','recovery'):
            page.goto('http://127.0.0.1:19190/'+key)
            file=E/('18-entra-msal-renewal.png' if key=='renewal' else 'pdf-'+key+'.png')
            page.locator('body').screenshot(path=str(file))
            manifest=[m for m in manifest if m['file']!=file.name]
            manifest.append(dict(file=file.name,source=page.url,description='Vista legible de evidencia ejecutada para PDF; no terminal simulada',at=datetime.now(timezone.utc).isoformat(),sha256=hashlib.sha256(file.read_bytes()).hexdigest()))
            print('CAPTURE',file.name,flush=True)
        browser.close()
    (E/'captures.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
finally:server.shutdown()
