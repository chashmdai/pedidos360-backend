"""Write docs/evidence/ep5/E-XX-<nombre>.txt (report section 15.2 format) from the raw outputs that
deploy/ep5-evidence.py produced on the EC2 (docs/evidence/ep5/aws/raw-*.json). Output is already redacted on the host;
this script redacts again as a second barrier. Usage: ep5-evidence-report.py E-XX raw-a.json[||raw-b.json] "observed" ["deviation"]
"""
import json
import re
import sys
from pathlib import Path
import aws_deploy as aws

OUT = aws.ROOT / "docs/evidence/ep5"
ENV_AWS = (f"AWS cuenta {aws.ACCOUNT} ({aws.REGION}), EC2 i-01bcf3ef9d3a64d4e (t3.large, Ubuntu 24.04), release "
           "ep5-20261119T040026Z; comandos ejecutados como root en /opt/pedidos360/current mediante SSM Run Command "
           "(AWS-RunShellScript, script revisado deploy/ep5-evidence.py). Kafka UI consultado por su API en 127.0.0.1:8090 "
           "desde la propia instancia (la misma vista que se abre por reenvío de puertos SSM).")
SPEC = {
    "E-01": ("arquitectura-kafka-compose", "Arquitectura Kafka levantada con Docker Compose",
             "Comprobar que los tres nodos ZooKeeper y los tres brokers se ejecutan en la instancia EC2.",
             "EP5: Compose Kafka con ZooKeeper y brokers. EP6: docker-compose en la nube; arquitectura Kafka (10 %).",
             "Seis contenedores (zookeeper-1..3, kafka-1..3) en estado running y healthy."),
    "E-02": ("ensamble-zookeeper", "Ensamble ZooKeeper con líder y seguidores",
             "Demostrar que los tres nodos forman un ensamble con quórum.", "EP6: arquitectura Kafka (10 %).",
             "Un nodo en modo leader y dos en modo follower."),
    "E-03": ("brokers-controlador", "Brokers registrados y controlador",
             "Comprobar el registro de los tres brokers y la existencia de un controlador.",
             "EP6: arquitectura Kafka (10 %); Kafka UI (5 %).",
             "Lista [1, 2, 3]; Kafka UI muestra tres brokers en línea y uno marcado como controlador."),
    "E-04": ("kafka-ui", "Kafka UI levantado y conectado",
             "Comprobar que Kafka UI se ejecuta con su Compose propio y administra el clúster.",
             "EP5: Compose de Kafka UI. EP6: Kafka UI (5 %).",
             "Contenedor kafka-ui healthy; clúster pedidos360 en línea con tres brokers y los tópicos de la sección 5."),
    "E-05": ("topicos-3x3", "Dos tópicos con tres particiones y tres réplicas",
             "Verificar particiones, réplicas, líderes e ISR de los tópicos de negocio.",
             "EP6: dos tópicos 3×3 en Kafka UI; justificación de tópicos (10 %).",
             "PartitionCount: 3 y ReplicationFactor: 3 en ambos; un líder distinto por partición; ISR con tres réplicas."),
    "E-06": ("parametros-topicos", "Parámetros de administración de tópicos",
             "Comprobar retención, política de limpieza y réplicas mínimas por flujo.",
             "EP5: parámetros de tópicos (12 %). EP6: administración de Kafka (15 %).",
             "orders.registered.v1: cleanup.policy=delete, retention.ms=604800000, min.insync.replicas=2. product-metrics.v1: "
             "cleanup.policy=compact, min.insync.replicas=2. DLT: retention.ms=1209600000."),
    "E-07": ("publicacion-pedido", "Publicación de un pedido en Kafka desde Orders",
             "Trazar un pedido desde la SPA hasta su mensaje en el tópico.",
             "EP5: productores (14 %). EP6: flujo de producción y consumo (12 %); diseño de eventos (6 %).",
             "HTTP 201; fila con published_at no nulo; log con tópico, partición y offset; mensaje con clave orderId y payload "
             "OrderRegisteredStreamV1 con sus líneas."),
    "E-08": ("grupos-consumidores", "Grupos de consumidores y distribución de particiones",
             "Mostrar los tres grupos, su asignación de particiones, offsets y lag.",
             "EP5: consumidores (14 %); consumer groups (12 %). EP6: métricas de offsets y lag (15 %).",
             "Agregador con tres miembros y una partición cada uno; monitor y vista con un miembro y tres particiones; lag 0 en reposo."),
    "E-09": ("reaccion-tiempo-real", "Reacción del sistema en cuasi tiempo real",
             "Demostrar que un nuevo pedido actualiza la vista y genera procesos derivados sin intervención.",
             "EP6: respuesta a eventos en tiempo real (12 %); casos de uso (15 %).",
             "En pocos segundos aumentan unidades, pedidos e importe de los productos; la métrica publicada incrementa version; "
             "aparece una alerta de alto valor."),
    "E-10": ("lag-recuperacion", "Lag y recuperación de un consumidor detenido",
             "Mostrar cómo el lag permite detectar un problema operacional y su resolución.",
             "EP6: métricas de offsets y lag (15 %); administración de Kafka (15 %).",
             "Con el servicio detenido, el grupo no tiene miembros y el lag total es 2. Tras el inicio, el lag vuelve a 0 y cada "
             "pedido se contabiliza una sola vez."),
    "E-11": ("payload-invalido-dlt", "Payload inválido derivado al DLT sin bloquear la partición",
             "Comprobar el tratamiento de mensajes defectuosos.", "EP5: manejo de errores (12 %).",
             "Log CONSUME_DLT sin reintentos; mensaje en pedidos360.orders.registered.v1.DLT con encabezados de tópico, partición, "
             "offset y excepción; el pedido válido posterior se procesa con normalidad."),
    "E-12": ("idempotencia-duplicado", "Idempotencia ante un evento duplicado",
             "Comprobar que una reentrega no duplica acumulados.", "EP5: manejo de errores (12 %); consumidores (14 %).",
             "Log CONSUME_DUPLICATE con el eventId; los acumulados no cambian."),
    "E-13": ("caida-broker", "Tolerancia a la caída de un broker",
             "Verificar la continuidad del servicio con un broker detenido.",
             "EP6: arquitectura Kafka (10 %); justificación de réplicas (10 %).",
             "Las particiones lideradas por el broker 2 cambian de líder; ISR de dos réplicas; el pedido se publica y procesa. "
             "Tras el inicio, el ISR vuelve a tres réplicas."),
    "E-14": ("kafka-admin", "Operaciones del microservicio administrador",
             "Ejercitar la administración de tópicos, configuraciones y grupos.",
             "EP5: administrador Kafka (6 %); administración de tópicos y grupos (6 %).",
             "201, 200, 200, 200 y 204 en la secuencia; 409 para el tópico de negocio; 403 para el rol User; detalle de grupo con "
             "offsets y lag por partición."),
    "E-15": ("reconstruccion-compactado", "Reconstrucción de la vista desde el tópico compactado",
             "Demostrar el uso de la compactación para recuperar estado.",
             "EP6: administración de Kafka (15 %); casos de uso (15 %).",
             "Tras el reinicio, el grupo de la vista relee product-metrics.v1 desde el inicio y presenta los mismos acumulados."),
    "E-16": ("rabbitmq-sin-cambios", "Integración RabbitMQ sin cambios",
             "Comprobar que el mismo pedido sigue procesándose por RabbitMQ.",
             "EP5 y EP6: Kafka complementa la arquitectura sin afectar RabbitMQ; dos nodos, tres colas con DLQ, exchanges direct y topic.",
             "Comprobante, auditoría y resumen con ACK; clúster de dos nodos sin particiones; tres colas con sus DLQ; exchanges "
             "direct y topic enlazados."),
    "E-17": ("api-gateway-jwt", "API Gateway y validación JWT de la nueva ruta",
             "Comprobar la protección de GET /api/v1/ventas/en-vivo.",
             "EP6: API Manager valida JWT; frontend consume a través del API Manager; OAuth 2.0/OIDC.",
             "HTTP 401 en los dos primeros casos; HTTP 200 con token válido emitido por Entra ID mediante authorization code con PKCE."),
    "E-18": ("pruebas-automatizadas", "Pruebas automatizadas",
             "Registrar el resultado de las pruebas de backend y frontend.",
             "EP5: el código compila, sigue buenas prácticas y responde a pruebas básicas.",
             "Build exitoso; las pruebas Java y React aprueban sin fallos, errores ni omisiones, y la compilación de producción del "
             "frontend finaliza correctamente."),
    "E-19": ("memoria-t3-large", "Uso de memoria en la instancia t3.large",
             "Contrastar el presupuesto de memoria con el consumo real.", "Dimensionamiento de la sección 13.",
             "Memoria disponible positiva sin uso sostenido de intercambio; contenedores bajo su mem_limit; servicios systemd activos."),
}


def redact(text):
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    text = re.sub(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+", "[JWT REDACTED]", text)
    return re.sub(r"assumed-role/voclabs/[^\s\"]+", "assumed-role/voclabs/[session]", text)


def render_step(step):
    body = step.get("out")
    if body is None:
        body = json.dumps(step.get("json"), ensure_ascii=False, indent=1)
    header = f"$ {step['cmd']}" + (f"   [exit {step['exit']}]" if step.get("exit") else "")
    return header + "\n" + "\n".join("    " + line for line in body.splitlines())


def main():
    eid, raws, observed = sys.argv[1], sys.argv[2], sys.argv[3]
    deviation = sys.argv[4] if len(sys.argv) > 4 else "Ninguna."
    name, title, objective, indicator, expected = SPEC[eid]
    environment, blocks = ENV_AWS, []
    for raw in filter(None, raws.split("||")):
        if raw.startswith("text:"):   # local textual source (e.g. E-18 build logs, gateway probes)
            path = aws.ROOT / raw[5:]
            blocks.append(f"--- {raw[5:]} ---\n" + path.read_text().rstrip())
            continue
        if raw.startswith("env:"):
            environment = raw[4:]
            continue
        data = json.loads((aws.EVIDENCE / raw).read_text())
        output = data["output"]
        assert isinstance(output, dict) and data["status"] == "Success", f"{raw}: remote action failed"
        blocks.append(f"--- {output['action']} {' '.join(output['args'])} @ {output['at']} (SSM {data['commandId']}) ---\n"
                      + "\n\n".join(render_step(s) for s in output["steps"]))
    text = (f"Evidencia {eid}. {title}\n\nObjetivo\n{objective}\n\nIndicador asociado\n{indicator}\n\nEntorno\n{environment}\n\n"
            f"Resultado esperado (informe)\n{expected}\n\nResultado observado\n{observed}\n\nDiferencias con el informe\n{deviation}\n\n"
            "Procedimiento y salida (sin secretos ni tokens)\n" + "\n\n".join(blocks) + "\n")
    path = OUT / f"{eid}-{name}.txt"
    path.write_text(redact(text))
    print(path.relative_to(aws.ROOT))


main()
