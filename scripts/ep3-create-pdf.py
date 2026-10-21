"""Simple A4 evidence document. All figures are previously verified screenshots."""
from pathlib import Path
from io import BytesIO
import json
from xml.sax.saxutils import escape
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak, Table, TableStyle, KeepTogether

ROOT=Path(__file__).resolve().parent.parent
E=ROOT/'docs/evidence/ep3'
DEST=ROOT/'docs/EP3_RABBITMQ_EVIDENCIAS.pdf'
baseline=json.loads((E/'baseline-before-ep3.json').read_text())
entra=json.loads((E/'entra-verification.json').read_text())
close=json.loads((E/'entra-browser-close.json').read_text())
assert baseline['backendModules']==['catalog-service','orders-service','bff']
assert entra['mode']=='MICROSOFT_ENTRA_REAL' and close['microsoftLogoutObserved'] and close['logoutButtons']==0
body=ParagraphStyle('Body',fontName='Helvetica',fontSize=11,leading=15,alignment=TA_JUSTIFY,spaceAfter=9)
head=ParagraphStyle('Head',parent=body,fontName='Helvetica-Bold',fontSize=14,leading=18,alignment=TA_LEFT,spaceAfter=12)
sub=ParagraphStyle('Sub',parent=body,fontName='Helvetica-Bold',fontSize=11.5,leading=15,alignment=TA_LEFT,spaceBefore=8,spaceAfter=7)
caption=ParagraphStyle('Caption',parent=body,fontSize=9,leading=12,alignment=TA_LEFT,textColor=colors.HexColor('#404040'),spaceAfter=10)
small=ParagraphStyle('Small',parent=body,fontSize=9,leading=12,alignment=TA_LEFT)
story=[]
def p(text):story.append(Paragraph(text,body))
def h(text):story.append(Paragraph(text,head))
def s(text):story.append(Paragraph(text,sub))
def page():story.append(PageBreak())
def fig(file,text,width=490,maxheight=460,crop=None):
    path=E/file
    source=str(path)
    with PILImage.open(path) as image:
        if crop:
            # Normal document cropping; original real screenshot stays intact.
            image=image.crop(crop)
            source=BytesIO();image.save(source,format='PNG');source.seek(0)
        w,h=image.size
    factor=min(width/w,maxheight/h)
    story.append(KeepTogether([Image(source,width=w*factor,height=h*factor),Spacer(1,5),Paragraph(text,caption)]))

h('Pedidos360 - Integración RabbitMQ, EP3')
story.append(Paragraph('Implementación y evidencias · 20 de octubre de 2026',caption))
s('1. Estado inicial del proyecto')
p('Antes de esta etapa tenía Catalog, Orders y BFF como módulos Spring Boot, un frontend React con TypeScript y MSAL, y MySQL con esquemas y usuarios separados. La aplicación permitía consultar productos, registrar pedidos multítem con snapshots de precio y consultar los pedidos del propietario. El BFF y los servicios validaban JWT de Microsoft Entra, scopes y roles.')
p('Reconstruí ese punto de partida a partir del README, la documentación previa y el commit '+baseline['commit'][:12]+', cuyo POM declara únicamente catalog-service, orders-service y bff. Guardé esa comprobación en baseline-before-ep3.json. El registro de pedidos era síncrono: todavía no había broker, outbox ni generación de comprobantes mediante un consumidor.')
s('2. Implementación de RabbitMQ')
p('Incorporé RabbitMQ 4.2.9 en un contenedor propio y agregué Receipts y un administrador REST. Elegí generar un comprobante interno de recepción después de registrar el pedido. No es una factura ni agrega pagos o reserva de stock. Mantengo el flujo anterior y uso la mensajería para una tarea posterior.')
p('Orders guarda el pedido y su evento en una outbox, dentro de la misma transacción MySQL. Un publicador envía el evento persistente y marca su publicación solo después del confirm del broker y de comprobar que no fue devuelto. Si RabbitMQ cae, el pedido permanece disponible y el evento queda pendiente.')
p('Centralicé nombres y declaraciones Queue, Exchange y Binding en messaging-support. Los contratos son técnicos; no compartí entidades ni un dominio global. Receipts valida el evento, persiste el comprobante y emite ACK manual. Un JSON inválido o un error permanente produce NACK sin requeue; un fallo transitorio admite hasta tres intentos y luego pasa a DLQ.')
p('El administrador REST delega en un servicio que usa la API Management de RabbitMQ. Solo permite recursos desechables pedidos360.lab.*, exige Admin y Orders.Read y rechaza eliminaciones de colas con datos o consumidores. Las credenciales quedan fuera de Git.')
p('Trabajé en WSL2 como codex. Usé puertos 19180-19184 para respetar el puerto 8181 ocupado por otro proyecto. Conservé MySQL, los datos, JWT/Entra y el diseño del frontend. React está autorizado por el docente. Esta etapa no ejecutó operaciones AWS ni creó gastos cloud.')

page(); h('3. Evidencias de funcionamiento'); s('Compilación y regresión')
p('Volví a ejecutar clean verify y las pruebas/build del frontend. Los 23 tests Java incluyen MySQL y RabbitMQ reales con Testcontainers, dominio, outbox con rollback, contratos HTTP y ACK/NACK. El frontend conserva sus 10 tests y su CSS sin cambios.')
fig('pdf-java.png','Figura 1. Resumen calculado de los XML Surefire reales y extracto del build Maven final. Cero fallos, errores u omitidos.',width=490,maxheight=355)
fig('pdf-react.png','Figura 2. Extractos de los tests y build React/TypeScript/Vite ejecutados en WSL. Estas vistas muestran archivos reales; no simulan una terminal.',width=490,maxheight=235)

page(); h('Broker y recursos de mensajería')
p('Usé un solo nodo, vhost, red y volumen exclusivos de Pedidos360. No presento este entorno como un clúster de alta disponibilidad. La cola de negocio y la DLQ son durables, con exchanges direct y bindings explícitos.')
fig('pdf-topology.png','Figura 3. Consulta real de la API Management: colas, contadores y bindings. Los mensajes conservados en DLQ son diagnósticos controlados.',width=490,maxheight=350)
fig('05c-rabbit-binding-table.png','Figura 4. Detalle real de Management: binding del exchange de Orders hacia la cola de Receipts. La fuente centralizada es pedidos-rabbit.properties.',width=490,maxheight=120)

page(); h('Pedido institucional y comprobante asíncrono')
p('Después de iniciar sesión con mi cuenta DUOC y completar el MFA, registré dos líneas por $30.970. El BFF y Orders devolvieron HTTP 201. Recargué la SPA y recuperé el pedido mediante HTTP 200. Lo correlacioné con su eventId, publicación confirmada y ACK de Receipts.')
fig('19-entra-order-form.png','Figura 5. Detalle del formulario real antes de enviarlo con la sesión institucional: dos líneas y total $30.970. El resultado del envío se acredita con HTTP 201 y la figura 6.',width=465,maxheight=326,crop=(20,305,995,845))
fig('pdf-flow.png','Figura 6. El mismo pedido tiene outbox publicada y comprobante durable. Los logs reales enlazan orderId/eventId con PUBLISH_CONFIRMED y ACK.',width=465,maxheight=295)

page(); h('ACK explícito, reintentos y errores diferenciados')
p('En una observación local controlada detuve únicamente Receipts. El mensaje quedó Ready; al reanudarlo con un fallo temporal de almacenamiento pasó a Unacked. Retiré el bloqueo y comprobé el archivo y el ACK. La demora temporal de cinco segundos se restauró a su valor original de un segundo.')
fig('14-message-unacked.png','Figura 7. Detalle Ready/Unacked de la captura real 14: una entrega durante el reintento. La imagen original y las capturas 13 y 15 conservan el contexto, antes y después.',width=490,maxheight=200,crop=(34,170,685,355))
fig('pdf-errors.png','Figura 8. Logs reales: éxito, duplicado idempotente, fallo transitorio, tres intentos agotados, contrato inválido y conflicto permanente. Las pruebas de fallo corresponden al fixture local.',width=490,maxheight=230)

page(); h('DLQ y administrador REST')
p('Comprobé que el consumidor rechaza sin requeue los mensajes no procesables. La respuesta real del broker conserva x-death con reason=rejected y el payload inválido. La consulta se hizo con requeue para no eliminar el mensaje diagnóstico.')
fig('pdf-dlq.png','Figura 9. Campos de una respuesta HTTP real de la DLQ, mostrados en una vista de evidencia. No es una reconstrucción de la interfaz Management.',width=490,maxheight=330)
fig('pdf-admin.png','Figura 10. Selección de respuestas reales del administrador: 201/200/204, validación 400, protección 403, inexistencia 404, conflicto 409 y broker caído 503. La autorización Admin 200 de esta prueba usa el fixture local.',width=490,maxheight=220)

page(); h('Microsoft Entra y protección de acceso')
p('La prueba institucional es independiente del fixture. El BFF verificó audience de la API, emisor Microsoft, versión 2.0, Catalog.Read, Orders.Read, Orders.Create y rol User. Catalog y Orders aceptaron las llamadas delegadas. No extraje tokens ni almacenamiento del navegador y no cambié registros, scopes o asignaciones.')
fig('pdf-security.png','Figura 11. Claims públicos mostrados por /me y access log sin cabeceras. La solicitud de renovación MSAL fue aceptada por el BFF; no prueba expiración natural.',width=490,maxheight=280)
fig('17-entra-admin-403.png','Figura 12. La cuenta User recibe HTTP 403 en la consulta administrativa. No elevé sus permisos para obtener un resultado distinto.',width=490,maxheight=150)
p('Microsoft confirmó el logout. Después intenté abrir /catalogo y la SPA volvió al inicio sin sesión. Las capturas 18, 21 y 22 registran renovación, logout y protección de rutas, sin contraseñas ni códigos MFA. No presento una sesión Admin Entra 200 que no ejecuté.')

page(); h('Recuperación y resultado final')
p('Detuve y reinicié solamente el broker propio, sin borrar el volumen. Durante la caída el sistema aceptó y recuperó un pedido; la outbox quedó pendiente y se procesó al volver RabbitMQ. El administrador respondió 503 durante la indisponibilidad. La aceptación completa aprobó 15 grupos y 48 aserciones HTTP.')
fig('pdf-recovery.png','Figura 13. Recuperación real del mismo contenedor/volumen y comprobación de hashes de los pedidos/líneas anteriores y del catálogo.',width=490,maxheight=265)
p('Incorporé procesamiento asíncrono durable y observable sin sustituir la creación de pedidos ni la seguridad anterior. Acredité el flujo local y el institucional con comprobante y ACK. El broker único y el store de un escritor no ofrecen HA ni exactamente una vez. El audit del lockfile preexistente conserva dos dependencias con severidad alta; no hice una actualización ajena al cierre.')
data=[[Paragraph('Indicador oficial',small),Paragraph('Peso',small),Paragraph('Evidencia principal',small)]]
for label,weight,proof in [('Nombres centralizados','12%','Fig. 3; properties'),('Beans Queue/Exchange/Binding','13%','Fig. 3-4; integración Rabbit'),('Configuración separada','10%','Configuraciones dedicadas; build'),('Listener por dominio','15%','Receipts; fig. 6-8'),('ACK, fallos y DLQ','20%','Fig. 7-9 y 13'),('Administrador REST','13%','Fig. 10; OpenAPI'),('Gestión encapsulada','10%','RabbitAdminService; tests'),('Validación de entrada','7%','HTTP 400/403/404/409/503')]:
    data.append([Paragraph(label,small),Paragraph(weight,small),Paragraph(proof,small)])
table=Table(data,colWidths=[200,40,255],hAlign='LEFT')
table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.5,colors.grey),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3)]))
story.append(table);story.append(Spacer(1,10))
p('Los porcentajes corresponden a la pauta, no a una calificación otorgada. El informe técnico, los contratos, scripts, trazas y capturas completas están en el backend. Mantengo ambos repositorios separados:')
story.append(Paragraph('<link href="https://github.com/chashmdai/pedidos360-backend" color="#174b78">https://github.com/chashmdai/pedidos360-backend</link><br/><link href="https://github.com/chashmdai/pedidos360-frontend" color="#174b78">https://github.com/chashmdai/pedidos360-frontend</link>',small))

def footer(canvas,doc):
    canvas.saveState();canvas.setFont('Helvetica',9);canvas.setFillColor(colors.HexColor('#555555'))
    canvas.drawRightString(A4[0]-48,24,str(doc.page));canvas.restoreState()
doc=SimpleDocTemplate(str(DEST),pagesize=A4,rightMargin=48,leftMargin=48,topMargin=40,bottomMargin=40,
    title='Pedidos360 - RabbitMQ EP3: implementación y evidencias',author='Pedidos360',pageCompression=1)
doc.build(story,onFirstPage=footer,onLaterPages=footer)
print('PDF:',DEST)
