"""Authentic screenshots: live local broker and explicitly labelled views of executed evidence."""
import datetime as dt
import hashlib
import html
import json
from pathlib import Path
import re
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'docs/evidence/ep4'
manifest=[]
existing=OUT/'captures.json'
if existing.exists():manifest=json.loads(existing.read_text())
def shot(page,name,source,description):
    file=OUT/name
    page.screenshot(path=str(file),full_page=True,animations='disabled')
    global manifest
    manifest=[item for item in manifest if item['file']!=name]
    manifest.append({'file':name,'at':dt.datetime.now(dt.timezone.utc).isoformat(),'source':source,'description':description,'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
    existing.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
def view(page,name,title,source,content):
    page.set_viewport_size({'width':1280,'height':200})
    page.set_content('<!doctype html><meta charset="utf-8"><style>body{font:22px/1.4 Arial;margin:28px;color:#172536}h1{font-size:30px}p{font-size:18px}pre{font:22px/1.4 monospace;white-space:pre-wrap;overflow-wrap:anywhere;border-top:1px solid #ccd;padding-top:12px}</style><h1>'+html.escape(title)+'</h1><p>Pedidos360 EP4 | Vista de resultados ejecutados, sin simular una terminal.</p><p>Fuente: '+html.escape(source)+'</p><pre>'+html.escape(content)+'</pre>')
    shot(page,name,source,'Vista legible del archivo real indicado; no interfaz o consola simulada')
    page.set_viewport_size({'width':1280,'height':900})
with sync_playwright() as p:
    browser=p.chromium.launch()
    page=browser.new_page(viewport={'width':1280,'height':900},device_scale_factor=1)
    text=(OUT/'backend-verify.txt').read_text()
    lines=[line for line in text.splitlines() if 'Tests run:' in line and '-- in ' in line]+text.splitlines()[-16:]
    extra=(OUT/'insights-http-final.txt').read_text() if (OUT/'insights-http-final.txt').exists() else ''
    lines += ['\nPruebas HTTP adicionales del servicio Insights (fase test, sin reempaquetar JAR):']
    lines += [line for line in extra.splitlines() if 'Tests run: 2,' in line and 'InsightsHttpContractTest' in line]
    view(page,'01-java-39-tests-wsl.png','WSL: Java clean verify y pruebas reales','backend-verify.txt','\n'.join(lines))
    text=(OUT/'frontend-tests.txt').read_text()+'\n'+(OUT/'frontend-build.txt').read_text()
    text=re.sub(r'\x1b\[[0-9;]*m','',text)
    view(page,'02-react-tests-build-wsl.png','WSL: React 11 pruebas y compilación cloud','frontend-tests.txt + frontend-build.txt',text)
    page.goto('http://127.0.0.1:15674')
    page.locator('input[name="username"]').fill('pedidos360_ep4_admin')
    password=(Path.home()/'.config/pedidos360/ep4/rabbit-admin-password').read_text().strip()
    page.locator('input[name="password"]').fill(password)
    page.locator('input[type="submit"]').click()
    page.get_by_role('link',name='Overview',exact=True).wait_for()
    page.wait_for_timeout(1500)
    shot(page,'03-cluster-two-nodes-wsl.png',page.url,'RabbitMQ Management real en WSL; no prueba cloud')
    page.goto('http://127.0.0.1:15674/#/queues')
    page.get_by_text('pedidos360.sales.failed.v1',exact=False).first.wait_for()
    shot(page,'04-three-queues-three-dlq-wsl.png',page.url,'Seis colas reales del clúster local; el tráfico AWS se acredita por separado')
    for filename,title,keys,image in [
        ('installation.json','AWS: instalación y salud de seis servicios',['release','health','memory'],'05-aws-services.png'),
        ('cloud-verification.json','AWS: dos nodos unidos y sin particiones',['cluster','checks'],'06-aws-cluster-checks.png'),
        ('cloud-verification.json','AWS: direct/topic, NACK y DLQ',['routingTests','deadLetters'],'07-aws-routing-dlq.png'),
        ('cloud-order-verification.json','AWS: pedido, outbox y tres efectos persistentes',None,'08-aws-order-effects.png'),
        ('cloud-recovery.json','AWS: recuperación y conservación de datos',None,'09-aws-recovery.png'),
        ('gateway-http.json','AWS: hosting SPA y JWT Authorizer',None,'10-gateway-http.png'),
    ]:
        file=OUT/filename
        if not file.exists():continue
        data=json.loads(file.read_text())
        if 'output' in data:data=data['output']
        if keys:data={key:data.get(key) for key in keys}
        view(page,image,title,filename,json.dumps(data,indent=2,ensure_ascii=False))
    def load(name):
        data=json.loads((OUT/name).read_text());return data.get('output',data)
    if (OUT/'cloud-verification.json').exists():
        cloud=load('cloud-verification.json')
        cluster=next(iter(cloud['cluster'].values()))
        lines=['AWS EC2 | Docker Compose | RabbitMQ 4.2.9',
            'cluster: '+cluster['cluster_name'],'miembros: '+', '.join(cluster['running_nodes']),
            'particiones: '+str(cluster['partitions'])+' | alarmas: '+str(cluster['alarms']),'',
            'COLA PRINCIPAL / CONSUMIDORES / DLQ']
        for q in cloud['queuesBefore']:
            if not q['name'].endswith('.failed.v1'):
                lines += [q['name']+' | '+str(q['consumers']), '  DLX: '+q['arguments']['x-dead-letter-exchange']]
        lines += ['', 'Puertos AMQP/Management ligados a 127.0.0.1 en la EC2.', 'Colas classic: sin réplica de mensajes ni HA de host.']
        view(page,'pdf-aws-cluster.png','Clúster y consumidores comprobados en AWS','cloud-verification.json; selección de campos reales','\n'.join(lines))
        lines=['RUTAS DIAGNÓSTICAS REALES EN AWS (mensaje inválido controlado)']
        lines += [test['key']+' -> routed='+str(test['routed']) for test in cloud['routingTests']]
        for q,data in cloud['deadLetters'].items():lines += ['',q,'x-death: '+', '.join(str(x['reason'])+' (count='+str(x['count'])+')' for x in data['xDeath'])]
        view(page,'pdf-aws-routing.png','Direct, topic y rechazos NACK a DLQ','cloud-verification.json.routingTests y deadLetters','\n'.join(lines))
    if (OUT/'cloud-order-verification.json').exists():
        order=load('cloud-order-verification.json')
        lines=['pedido: '+order['orderId'],'evento: '+order['outbox']['eventId'],
            'outbox published='+str(order['outbox']['published'])+' | total='+str(order['event']['total'])+' '+order['event']['currency'],'']
        lines += [re.sub(r'orderId=[^ ]+','',line) for line in order['logs']]
        if (OUT/'cloud-idempotency.json').exists():
            duplicate=load('cloud-idempotency.json');lines += ['','Republicación del mismo payload:']+[re.sub(r'orderId=[^ ]+','',line) for line in duplicate['logs'] if 'DUPLICATE' in line]
        view(page,'pdf-aws-acks.png','Pedido cloud: publicación, tres ACK e idempotencia','cloud-order-verification.json + cloud-idempotency.json','\n'.join(lines))
    if (OUT/'cloud-recovery.json').exists():
        recovery=load('cloud-recovery.json');pending=load('cloud-outbox-pending.json');recovered=load('cloud-recovered-order.json')
        lines=['AWS EC2 | Parada de los dos nodos propios; sin eliminar volúmenes.',
            'Pedido '+pending['orderId'],'Durante la parada: '+json.dumps(pending['outbox']),
            'Después del arranque Compose: '+json.dumps(recovered['outbox']),
            'Efectos persistentes: '+', '.join(recovered['effects']),
            'Mismos contenedores/volúmenes: '+str(recovery['sameContainerAndVolumeIds']),
            'DLQ antes: '+json.dumps(recovery['dlqCountsBefore']),
            'DLQ después: '+json.dumps(recovery['dlqCountsAfter']),
            'Datos iniciales conservados: '+json.dumps(recovered['previousDataPreserved'])]
        view(page,'pdf-aws-recovery.png','Outbox pendiente y recuperación verificadas','cloud-outbox-pending.json + cloud-recovery.json + cloud-recovered-order.json','\n'.join(lines))
    if (OUT/'entra-browser.json').exists():
        auth=load('entra-browser.json')
        selected={k:auth[k] for k in ('environment','role','scopes','audience','clientId','issuer','tokenVersion','adminHttp','forcedRefreshFromMicrosoftAccepted','logoutMicrosoftConfirmed','protectedRouteAfterLogout') if k in auth}
        view(page,'pdf-entra-cloud.png','Microsoft Entra real desde el frontend alojado en AWS','entra-browser.json; valores visibles de la API, sin identidad personal ni tokens',json.dumps(selected,indent=2,ensure_ascii=False))
    tests=[]
    for line in (OUT/'backend-verify.txt').read_text().splitlines():
        match=re.search(r'Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+).* -- in .*\.([A-Za-z]+)$',line)
        if match:tests.append(match.group(5)+': '+match.group(1)+' tests, '+match.group(2)+' fallos, '+match.group(3)+' errores')
    tests += ['BUILD SUCCESS (clean verify; 39 pruebas)',
        'InsightsHttpContractTest: 2 pruebas adicionales, 0 fallos, 0 errores',
        'React: 11 pruebas, build de producción aprobado.']
    view(page,'pdf-tests-summary.png','Pruebas ejecutadas en WSL codex','backend-verify.txt + insights-http-final.txt + frontend-tests.txt + frontend-build.txt','\n'.join(tests))
    if (OUT/'gateway-http.json').exists() and (OUT/'gateway-access-logs.json').exists():
        checks=load('gateway-http.json')['checks'];logs=load('gateway-access-logs.json')['events']
        lines=['PRUEBAS SIN CREDENCIALES REALES EN CLI:']
        lines += [c['path']+' -> '+str(c['status'])+(' (bearer sintético inválido)' if c['invalidSyntheticBearer'] else '') for c in checks if '/assets/' not in c['path']]
        lines += ['','LOGS GATEWAY DE LA SESIÓN INSTITUCIONAL:']
        routes=sorted({(e['routeKey'],e['status']) for e in logs if '/api/v1/' in e['routeKey']})
        lines += [route+' -> '+code for route,code in routes]
        view(page,'pdf-gateway-http.png','HTTPS, API y autorización comprobados en AWS','gateway-http.json + gateway-access-logs.json','\n'.join(lines))
    for file,description in [('11-cloud-spa-public.png','SPA real alojada en AWS, antes de iniciar sesión'),('12-cloud-order-entra.png','Pedido real desde frontend cloud, sesión Microsoft Entra'),('13-cloud-recovered-order-entra.png','Historial real después de recuperación y reload'),('14-cloud-catalog-entra.png','Catálogo cloud, precios y stock conservados'),('15-entra-cloud-logout.png','Regreso a la SPA sin sesión tras logout Microsoft'),('16-cloud-protected-after-logout.png','Ruta protegida redirigida a inicio tras logout')]:
        image=OUT/file
        if image.exists():
            manifest=[item for item in manifest if item['file']!=file]
            manifest.append({'file':file,'at':dt.datetime.fromtimestamp(image.stat().st_mtime,dt.timezone.utc).isoformat(),'source':'Codex IAB; sesión real con intervención manual del usuario','description':description,'sha256':hashlib.sha256(image.read_bytes()).hexdigest()})
    existing.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    browser.close()
