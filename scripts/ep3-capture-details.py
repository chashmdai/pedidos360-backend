"""Capture expanded Rabbit bindings and a preserved diagnostic DLQ message."""
from pathlib import Path
import hashlib
import json
import importlib.util
from http.server import ThreadingHTTPServer
import threading
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

E = Path(__file__).resolve().parent.parent/'docs/evidence/ep3'
with sync_playwright() as p:
    browser=p.chromium.launch()
    page=browser.new_page(viewport={'width':1380,'height':1150})
    page.goto('http://127.0.0.1:15672')
    page.locator('input[name="username"]').fill('pedidos360_ep3_admin')
    page.locator('input[name="password"]').fill((Path.home()/'.config/pedidos360/ep3/rabbit-admin-password').read_text().strip())
    page.locator('input[type="submit"]').click()
    page.get_by_role('link',name='Overview',exact=True).wait_for()
    print('Refresh control:',page.locator('select').evaluate_all('(els)=>els.map(e=>({id:e.id,name:e.name,options:Array.from(e.options).map(o=>({value:o.value,text:o.text}))}))'))
    # Use the UI option, not DOM content substitution, to stop automatic redraw.
    refresh=page.locator('select').filter(has=page.locator('option',has_text='No refresh'))
    if refresh.count(): refresh.first.select_option(label='No refresh')
    else:
        for select in page.locator('select').all():
            for option in select.locator('option').all():
                if 'Do not refresh' in (option.text_content() or ''):
                    select.select_option(value=option.get_attribute('value'))
                    break
    def shot(name,description,locator=None,full=True):
        path=E/name
        if locator is None: page.screenshot(path=str(path),full_page=full)
        else: locator.screenshot(path=str(path))
        manifest=json.loads((E/'captures.json').read_text())
        manifest=[m for m in manifest if m['file']!=name]
        manifest.append(dict(file=name,source=page.url,description=description,at=datetime.now(timezone.utc).isoformat(),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        (E/'captures.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
        print('CAPTURE',name,flush=True)
    page.goto('http://127.0.0.1:15672/#/queues/pedidos360-ep3/pedidos360.receipts.order-registered.v1')
    page.get_by_text('Bindings (2)',exact=True).click()
    page.get_by_text('order.registered.v1',exact=True).wait_for()
    shot('05b-rabbit-bindings.png','Bindings reales expandidos; exchange y routing key de negocio')
    shot('05c-rabbit-binding-table.png','Detalle real de la tabla de bindings; recorte nativo para legibilidad en PDF',
        locator=page.get_by_text('order.registered.v1',exact=True).locator('xpath=ancestor::table[1]'))
    page.goto('http://127.0.0.1:15672/#/queues/pedidos360-ep3/pedidos360.receipts.failed.v1')
    page.get_by_text('Get messages',exact=True).click()
    page.locator('select[name="ackmode"]').select_option('ack_requeue_true')
    page.locator('input[name="count"]').fill('1')
    page.get_by_role('button',name='Get Message(s)',exact=False).click()
    page.get_by_text('x-death',exact=False).first.wait_for()
    print('DLQ result headings:',page.locator('h2,h3,h4').all_text_contents())
    print('DLQ displayed x-death count:',page.get_by_text('x-death',exact=False).count())
    # The Management UI redraws its transient Get result while capturing. Preserve
    # an actual HTTP response and label its rendered JSON view explicitly instead.
    def load(name,file):
        spec=importlib.util.spec_from_file_location(name,Path(__file__).parent/file)
        result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
    runtime=load('capture_runtime','ep3-runtime.py')
    view=load('capture_view','ep3-capture.py')
    messages=runtime.broker_request('POST','queues/pedidos360-ep3/pedidos360.receipts.failed.v1/get',
        {'count':1,'ackmode':'ack_requeue_true','encoding':'auto','truncate':20000})
    assert messages and messages[0]['properties']['headers']['x-death'][0]['reason']=='rejected'
    (E/'dlq-message-detail.json').write_text(json.dumps(messages,indent=2)+'\n')
    view.evidence_page('dlq','DLQ · mensaje real y x-death rejected',
        'POST RabbitMQ /api/queues/pedidos360-ep3/pedidos360.receipts.failed.v1/get · ack_requeue_true · dlq-message-detail.json',
        json.dumps(messages,indent=2,ensure_ascii=False))
    server=ThreadingHTTPServer(('127.0.0.1',19190),view.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    page.goto('http://127.0.0.1:19190/dlq')
    shot('08b-dlq-message-xdeath.png','Vista de respuesta HTTP real de RabbitMQ; x-death rejected; no pantalla GUI simulada')
    server.shutdown()
    browser.close()
