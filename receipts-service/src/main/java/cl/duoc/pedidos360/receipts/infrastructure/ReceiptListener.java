package cl.duoc.pedidos360.receipts.infrastructure;

import cl.duoc.pedidos360.messaging.OrderRegisteredV1;
import cl.duoc.pedidos360.receipts.application.ReceiptStore;
import com.rabbitmq.client.Channel;
import java.io.IOException;
import org.slf4j.*;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;

@Component
public class ReceiptListener {
    private static final Logger log=LoggerFactory.getLogger(ReceiptListener.class);
    private final ReceiptStore store;
    private final JsonMapper json;
    private final int maxAttempts;
    private final long delay;
    public ReceiptListener(ReceiptStore store, JsonMapper json,
            @Value("${pedidos.receipts.max-attempts:3}") int maxAttempts,
            @Value("${pedidos.receipts.retry-delay-ms:1000}") long delay) {
        if (maxAttempts<1 || maxAttempts>5 || delay<0 || delay>10000) throw new IllegalArgumentException("Invalid retry bounds");
        this.store=store; this.json=json; this.maxAttempts=maxAttempts; this.delay=delay;
    }
    @RabbitListener(id="receipt-orders", queues="${pedidos.messaging.queue}", ackMode="MANUAL")
    public void receive(Message message, Channel channel) throws IOException {
        long tag=message.getMessageProperties().getDeliveryTag();
        OrderRegisteredV1 event;
        try {
            if (message.getBody().length>16384) throw new IllegalArgumentException("Oversized event");
            // An explicit type prevents arbitrary Java type headers from selecting a class.
            event=json.readValue(message.getBody(),OrderRegisteredV1.class);
            if (event==null || !event.eventId().toString().equals(message.getMessageProperties().getMessageId()))
                throw new IllegalArgumentException("Message identity mismatch");
        } catch (RuntimeException invalid) {
            channel.basicNack(tag,false,false);
            String id=message.getMessageProperties().getMessageId();
            String safeId=id!=null && id.matches("[0-9a-fA-F-]{36}")?id:"UNTRUSTED";
            log.warn("NACK_DLQ eventId={} reason=INVALID_CONTRACT deliveryTag={}",safeId,tag);
            return;
        }
        for (int attempt=1; attempt<=maxAttempts; attempt++) {
            boolean created;
            try {
                created=store.saveOnce(event);
            } catch (IOException temporary) {
                if (attempt==maxAttempts) {
                    channel.basicNack(tag,false,false);
                    log.warn("NACK_DLQ eventId={} orderId={} reason=RETRY_EXHAUSTED attempts={}",event.eventId(),event.orderId(),attempt);
                    return;
                }
                log.warn("RETRY eventId={} orderId={} reason=STORAGE_UNAVAILABLE attempt={} max={}",event.eventId(),event.orderId(),attempt,maxAttempts);
                try { Thread.sleep(delay); }
                catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt(); channel.basicNack(tag,false,false);
                    log.warn("NACK_DLQ eventId={} reason=INTERRUPTED",event.eventId()); return;
                }
                continue;
            } catch (RuntimeException permanent) {
                channel.basicNack(tag,false,false);
                log.warn("NACK_DLQ eventId={} orderId={} reason=PERMANENT_PROCESSING_ERROR",event.eventId(),event.orderId());
                return;
            }
            // Do not catch an ACK transport failure as a processing failure: let redelivery occur.
            channel.basicAck(tag,false);
            log.info("ACK eventId={} orderId={} result={} attempt={} redelivered={}",event.eventId(),event.orderId(),
                    created?"RECEIPT_STORED":"DUPLICATE",attempt,message.getMessageProperties().isRedelivered());
            return;
        }
    }
}
