package cl.duoc.pedidos360.orders.infrastructure.messaging;

import cl.duoc.pedidos360.messaging.MessagingProperties;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;
import org.slf4j.*;
import org.springframework.amqp.core.*;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
@ConditionalOnProperty(name="pedidos.messaging.enabled", havingValue="true")
public class OutboxPublisher {
    private static final Logger log=LoggerFactory.getLogger(OutboxPublisher.class);
    private final JdbcTemplate jdbc;
    private final RabbitTemplate rabbit;
    private final MessagingProperties topology;
    public OutboxPublisher(JdbcTemplate jdbc, RabbitTemplate rabbit, MessagingProperties topology) {
        this.jdbc=jdbc; this.rabbit=rabbit; this.topology=topology;
    }
    @Scheduled(fixedDelayString="${pedidos.messaging.publish-delay-ms:1000}", initialDelayString="${pedidos.messaging.initial-delay-ms:1000}")
    @Transactional
    public void publishPending() {
        // Row lock + SKIP LOCKED also prevents concurrent publishers selecting the same row.
        var rows=jdbc.queryForList("SELECT event_id,order_id,payload FROM order_event_outbox WHERE published_at IS NULL AND next_attempt_at<=CURRENT_TIMESTAMP(6) ORDER BY created_at LIMIT 10 FOR UPDATE SKIP LOCKED");
        for (var row:rows) {
            String id=row.get("event_id").toString();
            try {
                var properties=new MessageProperties();
                properties.setMessageId(id); properties.setContentType(MessageProperties.CONTENT_TYPE_JSON);
                properties.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
                var confirmation=new CorrelationData(id);
                rabbit.send(topology.exchange(),topology.routingKey(),
                        new Message(row.get("payload").toString().getBytes(StandardCharsets.UTF_8),properties),confirmation);
                var result=confirmation.getFuture().get(4,TimeUnit.SECONDS);
                if (!result.ack() || confirmation.getReturned()!=null) throw new IllegalStateException("Publication not routed/confirmed");
                jdbc.update("UPDATE order_event_outbox SET published_at=CURRENT_TIMESTAMP(6),attempts=attempts+1,last_error_code=NULL WHERE event_id=?",id);
                log.info("PUBLISH_CONFIRMED eventId={} orderId={}",id,row.get("order_id"));
            } catch (Exception failure) {
                if (failure instanceof InterruptedException) Thread.currentThread().interrupt();
                jdbc.update("UPDATE order_event_outbox SET attempts=attempts+1,next_attempt_at=DATE_ADD(CURRENT_TIMESTAMP(6),INTERVAL 5 SECOND),last_error_code='BROKER_UNCONFIRMED' WHERE event_id=?",id);
                log.warn("PUBLISH_DEFERRED eventId={} orderId={} reason=BROKER_UNCONFIRMED",id,row.get("order_id"));
            }
        }
    }
}
