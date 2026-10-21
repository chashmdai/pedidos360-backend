"""Capture the running local EP3, never Microsoft login, cookies or bearer tokens.

Run with the private evidence venv. Log pages are explicitly labelled as views
of executed evidence files, not fabricated terminal sessions. No app changes.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import re
import threading
import time
from urllib.parse import unquote

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "docs/evidence/ep3"
STATE = Path.home() / ".local/state/pedidos360-ep3"
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
MANIFEST = EVIDENCE / "captures.json"
PAGES = {}


def evidence_page(key, title, source, text):
    clean = ANSI.sub("", text)
    PAGES[key] = ("<!doctype html><html lang='es'><meta charset='utf-8'>"
        "<style>body{margin:30px;font:16px Arial;color:#182334;background:#fff}"
        "h1{font-size:24px;margin-bottom:8px}p{font-size:14px;color:#45546a}"
        "pre{font:15px/1.5 monospace;white-space:pre-wrap;overflow-wrap:anywhere;"
        "border-top:1px solid #ccd4df;padding-top:16px}</style>"
        f"<h1>{html.escape(title)}</h1><p>Pedidos360 EP3 · Evidencia ejecutada · "
        f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}</p>"
        f"<p>Vista de resultados reales. Fuente: {html.escape(source)}</p>"
        f"<pre>{html.escape(clean)}</pre></html>").encode()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        key = unquote(self.path).removeprefix("/")
        data = PAGES.get(key)
        self.send_response(200 if data else 404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data or b"Not found")

    def log_message(self, *_):
        pass


def source_pages():
    backend = (EVIDENCE / "backend-verify.txt").read_text()
    lines = [line for line in backend.splitlines() if "Tests run:" in line]
    lines += backend.splitlines()[-18:]
    evidence_page("java", "Java · clean verify y pruebas reales", "backend-verify.txt", "\n".join(lines))
    text = (EVIDENCE / "frontend-tests.txt").read_text() + "\n" + (EVIDENCE / "frontend-build.txt").read_text()
    evidence_page("frontend", "React · tests y build", "frontend-tests.txt + frontend-build.txt", text)
    report = json.loads((EVIDENCE / "runtime-verification.json").read_text())
    text = "MODO: " + report["mode"] + "\n\n"
    text += "\n".join(f"{r['method']:6} {r['port']} {r['path']}\n  esperado={r['expected']} recibido={r['actual']}" for r in report["httpTrace"] if r["port"] == 19184)
    evidence_page("admin", "Administrador REST · respuestas HTTP verificadas", "runtime-verification.json.httpTrace", text)
    logs = (STATE / "receipts-service.log").read_text().splitlines()
    producer = (STATE / "orders-service.log").read_text().splitlines()
    select = [line for line in logs if any(s in line for s in ("ACK eventId=", "RETRY eventId=", "NACK_DLQ"))]
    publish = [line for line in producer if "PUBLISH_CONFIRMED" in line]
    # Keep each actual log line, shortening only the logger/timestamp prefix.
    short = [re.sub(r"^.*?(?=(?:ACK |RETRY |NACK_DLQ |PUBLISH_CONFIRMED ))", "", x) for x in publish[-4:] + select[-18:]]
    evidence_page("acks", "Publicación, ACK, reintentos y NACK", "logs reales de orders-service y receipts-service; prefijos omitidos", "\n".join(short))
    text = "\n".join("PASS " + check["name"] for check in report["checks"])
    text += "\n\n" + (EVIDENCE / "controlled-broker-restart.txt").read_text()
    evidence_page("recovery", "Recuperación del broker y regresión", "runtime-verification.json + controlled-broker-restart.txt", text)
    evidence_page("receipt", "Pedido y comprobante asíncrono correlacionados", "runtime-verification.json; respuestas reales, modo local", json.dumps({"mode": report["mode"], "order": report["businessOrder"], "receipt": report["businessReceipt"]}, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    if args.probe:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto("http://127.0.0.1:15672")
            print("Chromium WSL:", browser.version, "Rabbit login page:", page.title())
            browser.close()
        return
    source_pages()
    server = ThreadingHTTPServer(("127.0.0.1", 19190), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    manifest = []

    def shot(page, name, source, description, full=False):
        path = EVIDENCE / name
        page.screenshot(path=str(path), full_page=full, animations="disabled")
        manifest.append(dict(file=name, source=source, description=description,
            at=datetime.now(timezone.utc).isoformat(), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        print("CAPTURE", name, flush=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(viewport={"width": 1380, "height": 1000}, device_scale_factor=1)
            page = context.new_page()
            for key, name in (("java", "01-java-tests.png"), ("frontend", "02-react-tests-build.png"),
                              ("admin", "09-admin-http.png"), ("acks", "07-ack-retry-nack.png"),
                              ("recovery", "10-broker-recovery.png"), ("receipt", "11-order-receipt.png")):
                page.goto("http://127.0.0.1:19190/" + key)
                shot(page, name, page.url, "Vista explícita de archivos/resultados ejecutados; no consola simulada", full=True)
            page.goto("http://127.0.0.1:15672")
            page.locator('input[name="username"]').fill("pedidos360_ep3_admin")
            password = (Path.home() / ".config/pedidos360/ep3/rabbit-admin-password").read_text().strip()
            page.locator('input[name="password"]').fill(password)
            page.locator('input[type="submit"]').click()
            page.get_by_role("link", name="Overview", exact=True).wait_for()
            page.wait_for_timeout(1500)
            shot(page, "03-rabbit-overview.png", page.url, "Broker propio operativo, un nodo")
            for route, name, text in (("exchanges", "04-rabbit-exchanges.png", "pedidos360.orders.events.v1"),
                                      ("queues", "05-rabbit-queues.png", "pedidos360.receipts.failed.v1"),
                                      ("queues/pedidos360-ep3/pedidos360.receipts.order-registered.v1", "05b-rabbit-bindings.png", "Bindings"),
                                      ("queues/pedidos360-ep3/pedidos360.receipts.failed.v1", "08-rabbit-dlq.png", "Overview")):
                page.goto("http://127.0.0.1:15672/#/" + route)
                page.get_by_text(text, exact=False).first.wait_for()
                page.wait_for_timeout(1200)
                shot(page, name, page.url, "Pantalla real de RabbitMQ Management", full=True)
            page.goto("http://127.0.0.1:5173")
            page.get_by_role("button", name="Entrar a la demostración").click()
            page.get_by_role("link", name="Catálogo", exact=True).click()
            page.get_by_text("Café de especialidad", exact=False).first.wait_for()
            shot(page, "12-frontend-catalog-local.png", page.url, "Frontend original, sesión fixture local explícita", full=True)
            page.get_by_role("link", name="Crear pedido", exact=False).first.click()
            quantities = page.locator('input[type="number"]')
            quantities.nth(0).fill("2")
            quantities.nth(1).fill("1")
            with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith("/api/v1/pedidos")) as response:
                page.get_by_role("button", name="Registrar pedido").click()
            assert response.value.status == 201
            order = response.value.json()
            page.get_by_role("heading", name="Mis pedidos").wait_for()
            page.get_by_text("PEDIDO / " + order["id"][:8].upper(), exact=False).first.wait_for()
            shot(page, "06-frontend-order-local.png", page.url, "Pedido creado en la SPA real con respuesta 201; modo local", full=True)
            # Resolve only the new order via the owned application's SQL helper; no owner/token in evidence.
            spec = importlib.util.spec_from_file_location("verify", ROOT / "scripts/verify-ep3.py")
            verify = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(verify)
            receipt = verify.wait_for(lambda: verify.delivered(order["id"]), "UI order receipt")
            (EVIDENCE / "ui-local-order.json").write_text(json.dumps({"mode":"LOCAL_SIGNED_FIXTURE_NOT_ENTRA", "http":201, "order":order, "receipt":receipt}, indent=2) + "\n")
            browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
