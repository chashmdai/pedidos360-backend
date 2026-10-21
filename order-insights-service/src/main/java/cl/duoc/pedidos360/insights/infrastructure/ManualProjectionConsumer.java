package cl.duoc.pedidos360.insights.infrastructure;
import cl.duoc.pedidos360.insights.application.ProjectionStore;
import cl.duoc.pedidos360.messaging.OrderRegisteredV1;
import com.rabbitmq.client.Channel;
import java.io.IOException;
import org.slf4j.*;
import org.springframework.amqp.core.Message;
import tools.jackson.databind.json.JsonMapper;

/** Shared transport policy for the two independent projections, without AMQP in their domain. */
public class ManualProjectionConsumer {
    private static final Logger log=LoggerFactory.getLogger(ManualProjectionConsumer.class);
    private final ProjectionStore store;
    private final JsonMapper json;
    private final String flow;
    private final int attempts;
    private final long delay;
    public ManualProjectionConsumer(ProjectionStore store,JsonMapper json,String flow,int attempts,long delay) {
        if (attempts<1 || attempts>5 || delay<0 || delay>10000) throw new IllegalArgumentException("Invalid retry bounds");
        this.store=store;this.json=json;this.flow=flow;this.attempts=attempts;this.delay=delay;
    }
    public void receive(Message message,Channel channel) throws IOException {
        long tag=message.getMessageProperties().getDeliveryTag();
        OrderRegisteredV1 event;
        try {
            if (message.getBody().length>16384) throw new IllegalArgumentException("Oversized event");
            event=json.readValue(message.getBody(),OrderRegisteredV1.class);
            if (event==null || !event.eventId().toString().equals(message.getMessageProperties().getMessageId()))
                throw new IllegalArgumentException("Message identity mismatch");
        } catch (RuntimeException invalid) {
            channel.basicNack(tag,false,false);
            log.warn("NACK_DLQ flow={} reason=INVALID_CONTRACT deliveryTag={}",flow,tag);return;
        }
        for (int attempt=1;attempt<=attempts;attempt++) {
            boolean created;
            try { created=store.saveOnce(event); }
            catch (IOException transientFailure) {
                if (attempt==attempts) {
                    channel.basicNack(tag,false,false);
                    log.warn("NACK_DLQ flow={} eventId={} reason=RETRY_EXHAUSTED attempts={}",flow,event.eventId(),attempt);return;
                }
                log.warn("RETRY flow={} eventId={} reason=STORAGE_UNAVAILABLE attempt={}",flow,event.eventId(),attempt);
                try { Thread.sleep(delay); }
                catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();channel.basicNack(tag,false,false);
                    log.warn("NACK_DLQ flow={} eventId={} reason=INTERRUPTED",flow,event.eventId());return;
                }
                continue;
            } catch (RuntimeException permanent) {
                channel.basicNack(tag,false,false);
                log.warn("NACK_DLQ flow={} eventId={} reason=PERMANENT_PROCESSING_ERROR",flow,event.eventId());return;
            }
            // A transport failure here must escape, so the unacknowledged message can be redelivered.
            channel.basicAck(tag,false);
            log.info("ACK flow={} eventId={} orderId={} result={} attempt={}",flow,event.eventId(),event.orderId(),created?"PROJECTION_STORED":"DUPLICATE",attempt);
            return;
        }
    }
}
