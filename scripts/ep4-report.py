"""Create the complementary EP4 PDF from checked-in, real execution evidence.

Run with the evidence venv (ReportLab, Pillow, pypdf). No AWS operations,
browser sessions, synthetic screenshots or credentials are used here.
"""
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image, Table, TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/evidence/ep4'
OUTPUT = ROOT / 'docs/EP4_IMPLEMENTACION_EVIDENCIAS.pdf'
WIDTH = A4[0] - 96
INK = colors.HexColor('#20252a')
MUTED = colors.HexColor('#52606b')
styles = {
    'body': ParagraphStyle('body', fontName='Helvetica', fontSize=11,
                           leading=15.1, alignment=TA_JUSTIFY,
                           textColor=INK, spaceAfter=9),
    'title': ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=17,
                            leading=21, spaceAfter=14, textColor=INK),
    'h2': ParagraphStyle('h2', fontName='Helvetica-Bold', fontSize=12,
                         leading=16, spaceBefore=7, spaceAfter=8, textColor=INK),
    'caption': ParagraphStyle('caption', fontName='Helvetica', fontSize=9,
                              leading=12, textColor=MUTED, spaceAfter=9),
    'small': ParagraphStyle('small', fontName='Helvetica', fontSize=9.5,
                            leading=12.5, spaceAfter=9, textColor=MUTED),
    'cell': ParagraphStyle('cell', fontName='Helvetica', fontSize=9.4,
                           leading=12.5, alignment=TA_LEFT, textColor=INK),
}
story = []


def p(text, style='body'):
    story.append(Paragraph(text, styles[style]))


def heading(text):
    p(text, 'title')


def figure(name, caption, width=475):
    path = EVIDENCE / name
    with PILImage.open(path) as source:
        height = width * source.height / source.width
    picture = Image(str(path), width=width, height=height)
    picture.hAlign = 'CENTER'
    story.extend([picture, Spacer(1, 5)])
    p(caption, 'caption')


def table(rows, widths):
    data = [[Paragraph(escape(str(cell)), styles['cell']) for cell in row]
            for row in rows]
    result = Table(data, colWidths=widths, hAlign='LEFT')
    result.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#edf0f2')),
        ('LINEBELOW', (0, 0), (-1, 0), .5, colors.HexColor('#adb5bd')),
        ('LINEBELOW', (0, 1), (-1, -1), .3, colors.HexColor('#dce1e5')),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.extend([result, Spacer(1, 10)])


def page():
    story.append(PageBreak())


heading('Pedidos360: evolución técnica EP4')
p('Implementación y evidencias complementarias a EP3 | 21 de octubre de 2026', 'small')
p('Partí de la versión EP3 publicada: Catalog y Orders con MySQL, BFF con JWT, '
  'React con MSAL y el flujo Orders → outbox → RabbitMQ → Receipts. Conservé '
  'esa implementación, su historial y su PDF. Esta iteración incorpora un clúster '
  'real, dos usos adicionales del evento y el frontend alojado en AWS.')
p('Elegí reutilizar el evento de pedido registrado. Además del comprobante, '
  'guardo una auditoría inmutable y construyo un resumen diario UTC de importes '
  'solicitados por moneda. Son proyecciones independientes; el resumen no '
  'representa pagos ni reserva de stock. No cambié el agregado Order, sus '
  'snapshots, el contrato REST ni el diseño visual.')
table([
    ('Flujo', 'Componente', 'Nuevo alcance'),
    ('Comprobante', 'receipts-service', 'Conservé el consumo del exchange direct y su DLQ.'),
    ('Auditoría', 'order-insights-service', 'Registro persistente único por evento, con cola y DLQ propias.'),
    ('Resumen diario', 'order-insights-service', 'Importes agrupados por día y moneda, sin duplicar redeliveries.'),
], [100, 133, WIDTH - 233])
p('Arquitectura desplegada', 'h2')
p('El navegador accede por HTTPS a API Gateway. La integración existente '
  'VPC Link → ALB interno → BFF sirve la SPA en /app/ y mantiene las API '
  'protegidas. Catalog y Orders utilizan RDS. Orders conserva su outbox '
  'transaccional y publica en el direct; un binding hacia el topic distribuye '
  'también a auditoría y resumen. Los tres consumidores confirman después '
  'de guardar su efecto persistente.')
p('Reutilicé EC2 i-0818fdfafcfb7cb31 (t3.medium), RDS pedidos360-mysql, '
  'el Gateway 7k2zyh0t0d y la red propia en us-east-1. No amplié capacidad '
  'ni añadí servicios cloud facturables. La operación de los recursos '
  'existentes sigue teniendo costo. No cambié reglas Security Group ni rutas '
  'previas del laboratorio.')
p('Conservo seis servicios Spring activos, dos nodos RabbitMQ en Docker '
  'Compose y datos persistentes. AMQP, Management e interfaces administrativas '
  'quedan en loopback; no abrí esos puertos a Internet.')
p('Fuentes reproducibles: EP4_IMPLEMENTACION.md, EP4_OPERACION.md, '
  'EP4_TRAZABILIDAD.md y docs/evidence/ep4/. Las vistas de resultados incluidas '
  'más adelante identifican el archivo real del que proceden; no simulan terminales.', 'small')

page()
heading('Clúster, tres flujos y enrutamiento')
p('Desplegué RabbitMQ 4.2.9 con Compose en EC2. Comprobé los dos miembros '
  'sin particiones, con el productor conectado al nodo 2 y los consumidores '
  'al nodo 1.')
figure('pdf-aws-cluster.png', 'Figura 1. Estado real obtenido por SSM y API Management '
       'en AWS: dos miembros y un consumidor por cola principal.')
p('Enlacé el direct al topic. Los patrones order.registered.* y *.registered.v1 '
  'alimentan auditoría y resumen; comprobé destinos selectivos y una clave sin ruta.')
figure('pdf-aws-routing.png', 'Figura 2. Pruebas de routing ejecutadas en AWS y '
       'x-death=rejected en cada DLQ tras mensajes inválidos controlados.')
page()
heading('Frontend cloud integrado con pedidos')
p('Compilé React con base /app/ y adapté únicamente BrowserRouter y las URI '
  'de MSAL. El BFF sirve esos archivos desde EC2 a través del Gateway. '
  'Contrasté los hashes de HTML, JavaScript y CSS recibidos por HTTPS con el '
  'release; la prueba no depende de Vite ni de localhost.')
figure('12-cloud-order-entra.png', 'Figura 3. Aplicación real alojada en AWS, '
       'con sesión institucional. Registré dos líneas por 30.970 CLP; el pedido '
       'quedó disponible en el historial.', width=482)
p('Desde la misma SPA consulté el catálogo y recuperé pedidos. La creación '
  'respondió 201 y las consultas 200 en el log de API Gateway. El pedido '
  'cee13d49-4bd2-43be-bc85-7c700b3d37a5 originó el evento correlacionado '
  'con los tres consumidores en la siguiente evidencia.')
p('Acceso cloud: <link href="https://7k2zyh0t0d.execute-api.us-east-1.amazonaws.com/app/" '
  'color="#245478">https://7k2zyh0t0d.execute-api.us-east-1.amazonaws.com/app/</link>', 'small')

page()
heading('ACK, duplicados y recuperación')
p('Comprobé tres efectos persistentes y sus ACK explícitos. Al republicar '
  'el mismo payload, los tres consumidores confirmaron DUPLICATE sin '
  'cambiar archivos ni conteos.')
figure('pdf-aws-acks.png', 'Figura 4. Publicación confirmada, tres ACK y '
       'republicación idempotente del pedido institucional en AWS.')
p('Detuve ambos nodos propios y registré otro pedido por 21.980 CLP. '
  'La outbox quedó pendiente; al recuperar los mismos contenedores y '
  'volúmenes obtuve los tres efectos y ACK.')
figure('pdf-aws-recovery.png', 'Figura 5. Observé ocho intentos pendientes y '
       'publicación en el doce. Se conservaron las DLQ, archivos y hashes '
       'de las filas iniciales. Es recuperación temporal, no failover.')

page()
heading('Microsoft Entra y seguridad del Gateway')
p('Inicié sesión institucional manualmente con las aplicaciones existentes '
  'y la URI cloud aprobada. La API aceptó token v2, audience propia, tres '
  'scopes y User; también aceptó la renovación solicitada.')
figure('pdf-entra-cloud.png', 'Figura 6. Registro seguro de la comprobación '
       'institucional: User recibe 403 en administración; logout y ruta protegida '
       'comprobados. No contiene el token ni identidad personal.')
p('Conservé las siete rutas API con JWT/scopes; solo los GET de la SPA '
  'son públicos. Comprobé 401 sin JWT o con bearer inválido y protección '
  'de /app/catalogo después del logout.')
figure('pdf-gateway-http.png', 'Figura 7. HTTP reales: acceso a archivos cloud, '
       'rechazos 401 y registros 200/201/403 de API Gateway.')

page()
heading('Pruebas automatizadas y administración')
p('Ejecuté el build en WSL2 como codex, con MySQL y RabbitMQ reales en '
  'Testcontainers. El clean verify aprobó 39 pruebas Java. Una pasada HTTP '
  'posterior añadió dos pruebas nuevas de Insights: son 41 distintas; '
  'no vuelvo a sumar las doce repetidas del módulo. React aprobó 11 pruebas '
  'y su build de producción.')
figure('pdf-tests-summary.png', 'Figura 8. Resumen de los logs reales '
       'backend-verify.txt, insights-http-final.txt, frontend-tests.txt y '
       'frontend-build.txt. Cero fallos, errores u omitidas en Java.')
p('Conservé el administrador REST y añadí PATCH de políticas TTL/longitud '
  'máxima para colas descartables pedidos360.lab.*. Comprobé HTTP 200, '
  'validación de vacíos/rangos, JWT/rol/scopes, namespace protegido 403 y '
  'conflicto 409 cuando los argumentos inmutables tienen precedencia. No '
  'elimino/recreo colas de negocio para simular una actualización.')
p('Los consumidores distinguen contrato inválido o conflicto permanente '
  '(NACK sin requeue) de IOException (hasta tres intentos y después DLQ). '
  'Estas fallas de almacenamiento y los HTTP 200 Admin se probaron localmente '
  'con fixtures y broker real. En AWS comprobé NACK/DLQ, duplicados, reconexión '
  'y la outbox; no atribuyo allí los ensayos locales.')
p('Comandos reproducibles', 'h2')
p('bash scripts/ep4-build.sh all<br/>bash scripts/ep4-insights-http-test.sh<br/>'
  'bash scripts/ep4.sh inspect<br/>bash scripts/ep4.sh ssm '
  'deploy/ep4-final-verification.py --output final-check.json', 'small')
p('Los hashes de los seis JAR instalados coinciden con release-manifest.json. '
  'RDS conservó TLS con VERIFY_IDENTITY, Flyway y usuarios de aplicación sin '
  'DDL. Las filas previas no cambiaron: añadí solo dos pedidos de prueba.')

page()
heading('Resultado y alcance comprobado')
p('La iteración conserva EP3 y amplía el procesamiento de un pedido a tres '
  'resultados asíncronos. Verifiqué la SPA y seis servicios en AWS, dos nodos '
  'RabbitMQ integrados, enrutamiento direct/topic, tres DLQ, idempotencia y '
  'recuperación. Mantengo trazabilidad detallada de P01-P11 y de los ocho '
  'indicadores en EP4_TRAZABILIDAD.md; esta síntesis no asigna una nota.')
table([
    ('Indicador', 'Peso', 'Evidencia de esta iteración'),
    ('R1: configuración centralizada', '12%', 'pedidos-rabbit.properties y bindings efectivos en AWS.'),
    ('R2: recursos AMQP', '13%', 'Beans Queue/Exchange/Binding y tres colas con DLQ.'),
    ('R3: separación', '10%', 'Configuración AMQP separada; dominio y REST conservados.'),
    ('R4: consumidores', '15%', 'Receipts, auditoría y resumen: tres efectos y ACK en AWS.'),
    ('R5: fallos y confirmación', '20%', 'NACK/DLQ, duplicados, outbox y recuperación; IOException local.'),
    ('R6: administrador REST', '13%', 'HTTP con broker real en WSL; desplegado privado en AWS.'),
    ('R7: operaciones y actualización', '10%', 'CRUD, bindings y políticas acotadas; 409 sin recrear.'),
    ('R8: validación', '7%', 'Tests HTTP de entradas, límites, namespace y autorización.'),
], [176, 40, WIDTH - 216])
p('Límites y comprobaciones no ejecutadas', 'h2')
p('No hay HA ni réplica classic; tampoco probé pérdida permanente del host. '
  'No ejecuté login real de la cuenta Admin ni expiración natural: Graph '
  'acredita su asignación existente y User real acredita el 403. El tenant '
  'institucional era preexistente, no lo creé en EP4. Las dos alertas altas '
  'npm ya documentadas en EP3 siguen pendientes; no añadí dependencias npm. '
  'Las proyecciones por archivos están pensadas para un escritor y este '
  'volumen de laboratorio, no para analítica de alto volumen.')
p('Repositorios y documentación', 'h2')
p('<link href="https://github.com/chashmdai/pedidos360-backend" color="#245478">'
  'github.com/chashmdai/pedidos360-backend</link><br/>'
  '<link href="https://github.com/chashmdai/pedidos360-frontend" color="#245478">'
  'github.com/chashmdai/pedidos360-frontend</link>', 'small')
p('El backend conserva el informe EP3 y añade este complemento, las fuentes '
  'de las evidencias, scripts de operación y contratos. EP4_OPERACION.md '
  'describe cómo renovar credenciales, reconciliar y usar el despliegue '
  'existente sin recrear infraestructura.', 'small')


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor('#d5dade'))
    canvas.setLineWidth(.4)
    canvas.line(48, 35, A4[0] - 48, 35)
    canvas.setFillColor(MUTED)
    canvas.setFont('Helvetica', 8)
    canvas.drawString(48, 23, 'Pedidos360 | Complemento técnico EP4 | 21-10-2026')
    canvas.drawRightString(A4[0] - 48, 23, str(doc.page))
    canvas.restoreState()


if __name__ == '__main__':
    document = SimpleDocTemplate(str(OUTPUT), pagesize=A4, rightMargin=48,
        leftMargin=48, topMargin=43, bottomMargin=46,
        title='Pedidos360 - Implementación y evidencias EP4',
        author='Pedidos360', subject='Evolución técnica complementaria a EP3',
        pageCompression=1)
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    from pypdf import PdfReader
    pdf = PdfReader(OUTPUT)
    assert len(pdf.pages) == 7, f'Unexpected layout: {len(pdf.pages)} pages; render and adjust'
    print(f'{OUTPUT.name}: {len(pdf.pages)} A4 pages, {OUTPUT.stat().st_size} bytes')
