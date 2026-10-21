"""Capture actual Ready/Unacked states using only this runtime's Receipts PID.

Creates one labelled fixture order. Never deletes queued messages or old data.
The controlled filesystem blocker is removed in finally; retry delay is restored.
"""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from datetime import datetime, timezone
import hashlib
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
E = ROOT / 'docs/evidence/ep3'


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


runtime = module('ep3_runtime_observe', 'ep3-runtime.py')
verify = module('verify_observe', 'verify-ep3.py')
owned = runtime.records()
assert owned['receipts-service']['mode'] == 'local', 'Observation is a local fixture test only'
record = owned['receipts-service']
blocker = None


def stop_receipts():
    record = runtime.records()['receipts-service']
    assert runtime.running(record), 'Receipt process identity changed; refusing to signal'
    os.killpg(record['pid'], signal.SIGTERM)
    verify.wait_for(lambda: not runtime.running(record), 'only owned Receipts exits', 20)


def start_receipts(delay):
    components = json.loads((runtime.CONFIG / 'components.json').read_text())
    env = dict(os.environ, **components['receipts-service'], SPRING_PROFILES_ACTIVE='local,ep3',
        SERVER_PORT='19183', SERVER_ADDRESS='127.0.0.1', RABBIT_HOST='127.0.0.1',
        RABBIT_PORT='5672', RABBIT_VHOST='pedidos360-ep3', PEDIDOS_RECEIPTS_RETRY_DELAY_MS=str(delay))
    command = ['/usr/bin/java', '--enable-native-access=ALL-UNNAMED', '-Djava.net.preferIPv4Stack=true',
        '-Xms32m', '-Xmx256m', '-jar', str(Path.home()/'.cache/pedidos360-ep3/build/receipts-service/receipts-service-0.1.0-SNAPSHOT.jar')]
    with (runtime.STATE/'receipts-service.log').open('a') as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    records = runtime.records()
    records['receipts-service'] = dict(pid=process.pid, fingerprint=runtime.fingerprint(process.pid), port=19183, mode='local')
    runtime.MANIFEST.write_text(json.dumps(records, indent=2))
    return process


def capture(page, name, description):
    path = E / name
    page.screenshot(path=str(path), full_page=True, animations='disabled')
    captures = json.loads((E/'captures.json').read_text())
    captures.append(dict(file=name, source=page.url, description=description, at=datetime.now(timezone.utc).isoformat(),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    (E/'captures.json').write_text(json.dumps(captures, indent=2, ensure_ascii=False)+'\n')
    print('CAPTURE', name, flush=True)


try:
    stop_receipts()
    order = verify.api(19180, '/api/v1/pedidos', 201, 'POST', {'items':[
        {'productoId':'10000000-0000-0000-0000-000000000001','cantidad':1}]})
    row = verify.wait_for(lambda: (r if (r:=verify.outbox(order['id']))['published'] else None), 'publisher confirmed without consumer')
    queue = verify.TOP['queue']
    verify.wait_for(lambda: verify.broker('GET','queues/pedidos360-ep3/'+queue)['messages_ready'] > 0, 'Ready state', 20)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width':1380,'height':1000})
        page.goto('http://127.0.0.1:15672')
        page.locator('input[name="username"]').fill('pedidos360_ep3_admin')
        page.locator('input[name="password"]').fill(runtime.secret('rabbit-admin'))
        page.locator('input[type="submit"]').click()
        page.get_by_role('link',name='Overview',exact=True).wait_for()
        page.goto('http://127.0.0.1:15672/#/queues/pedidos360-ep3/'+queue)
        page.get_by_text('Consumers',exact=False).first.wait_for()
        capture(page, '13-message-ready.png', 'Pedido real persistido/publicado, consumidor propio temporalmente detenido: Ready')
        blocker = runtime.STATE/'receipts'/(row['eventId']+'.json')
        blocker.mkdir()
        start_receipts(5000)
        verify.wait_for(lambda: verify.logs_contain('RETRY eventId='+row['eventId']), 'controlled transient storage error', 30)
        verify.wait_for(lambda: verify.broker('GET','queues/pedidos360-ep3/'+queue)['messages_unacknowledged'] > 0, 'Unacked state', 8)
        page.reload()
        page.get_by_text('Consumers',exact=False).first.wait_for()
        capture(page, '14-message-unacked.png', 'Entrega real Unacked durante reintento controlado; demora temporal de cinco segundos')
        blocker.rmdir()
        verify.wait_for(lambda: verify.delivered(order['id']), 'real receipt after recovery', 20)
        verify.wait_for(lambda: verify.logs_contain('ACK eventId='+row['eventId']), 'explicit manual ACK', 20)
        verify.wait_for(lambda: verify.broker('GET','queues/pedidos360-ep3/'+queue)['messages_unacknowledged'] == 0, 'no outstanding ACK', 20)
        page.reload()
        page.get_by_text('Consumers',exact=False).first.wait_for()
        capture(page, '15-message-acked.png', 'Almacenamiento recuperado, ACK explícito y cola sin entregas pendientes')
        page.goto('http://127.0.0.1:15672/#/queues/pedidos360-ep3/'+verify.TOP['dead-queue'])
        page.get_by_text('Get messages',exact=True).click()
        # The default is requeue; explicitly select it before reading our diagnostic message.
        mode = page.locator('select[name="ackmode"]')
        mode.select_option('ack_requeue_true')
        page.locator('input[name="count"]').fill('1')
        page.get_by_role('button',name='Get Message(s)',exact=False).click()
        page.get_by_text('x-death',exact=False).first.wait_for()
        capture(page, '08b-dlq-message-xdeath.png', 'Mensaje real en DLQ, x-death; consulta con requeue conserva el mensaje')
        browser.close()
    (E/'delivery-observation.json').write_text(json.dumps(dict(orderId=order['id'],eventId=row['eventId'],
        states=['Ready','Unacked during retry','ACK after storage'],temporaryRetryDelayMs=5000,restoredRetryDelayMs=1000),indent=2)+'\n')
finally:
    if blocker is not None and blocker.is_dir(): blocker.rmdir()
    current = runtime.records()['receipts-service']
    if runtime.running(current): stop_receipts()
    start_receipts(1000)
    print('Restored only owned Receipts with original 1000 ms retry delay.',flush=True)
