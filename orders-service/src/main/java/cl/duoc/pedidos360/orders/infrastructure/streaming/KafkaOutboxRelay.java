package cl.duoc.pedidos360.orders.infrastructure.streaming;

import cl.duoc.pedidos360.kafka.KafkaTopicProperties;
import cl.duoc.pedidos360.kafka.OrderRegisteredStreamV1;
import java.util.ArrayList;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.json.JsonMapper;

/**
 * Publishes order_stream_outbox to pedidos360.orders.registered.v1 with key orderId. A row is marked
 * published only after the broker confirms the write with acks=all; otherwise it is retried in 5 s.
 * Independent of the RabbitMQ OutboxPublisher: each outbox has its own table and publisher.
 */
@Component
@ConditionalOnProperty(name = "pedidos.kafka.enabled", havingValue = "true")
public class KafkaOutboxRelay {
    private static final Logger log = LoggerFactory.getLogger(KafkaOutboxRelay.class);
    private final JdbcTemplate jdbc;
    private final KafkaTemplate<String, Object> kafka;
    private final JsonMapper json;
    private final String topic;
    private final int batchSize;
    private final long confirmTimeoutMs;

    public KafkaOutboxRelay(JdbcTemplate jdbc, KafkaTemplate<String, Object> kafka, JsonMapper json, KafkaTopicProperties topics,
                            @Value("${pedidos.kafka.relay.batch-size:20}") int batchSize,
                            @Value("${pedidos.kafka.relay.confirm-timeout-ms:35000}") long confirmTimeoutMs) {
        this.jdbc = jdbc; this.kafka = kafka; this.json = json; this.topic = topics.ordersRegistered();
        this.batchSize = batchSize; this.confirmTimeoutMs = confirmTimeoutMs;
    }

    private record Pending(String eventId, String orderId, CompletableFuture<SendResult<String, Object>> confirmation) {}

    @Scheduled(fixedDelayString = "${pedidos.kafka.relay.delay-ms:1000}", initialDelayString = "${pedidos.kafka.relay.initial-delay-ms:1000}")
    @Transactional
    public void publishPending() {
        // Row lock + SKIP LOCKED: concurrent relays never select the same row.
        var rows = jdbc.queryForList("SELECT event_id,order_id,payload FROM order_stream_outbox WHERE published_at IS NULL "
                + "AND next_attempt_at<=CURRENT_TIMESTAMP(6) ORDER BY created_at LIMIT ? FOR UPDATE SKIP LOCKED", batchSize);
        var pending = new ArrayList<Pending>(rows.size());
        Exception unavailable = null;
        for (var row : rows) {
            String eventId = row.get("event_id").toString(), orderId = row.get("order_id").toString();
            CompletableFuture<SendResult<String, Object>> confirmation;
            if (unavailable != null) {
                // The producer could not even accept a record (e.g. no metadata): defer the rest of the batch.
                confirmation = CompletableFuture.failedFuture(unavailable);
            } else {
                OrderRegisteredStreamV1 event = null;
                try {
                    event = json.readValue(row.get("payload").toString(), OrderRegisteredStreamV1.class);
                } catch (RuntimeException invalid) {
                    // Unreadable payload: only this row is deferred.
                }
                if (event == null) {
                    confirmation = CompletableFuture.failedFuture(new IllegalStateException("Unreadable stream outbox payload"));
                } else {
                    try {
                        confirmation = kafka.send(topic, event.orderId().toString(), event);
                    } catch (RuntimeException failure) {
                        unavailable = failure;
                        confirmation = CompletableFuture.failedFuture(failure);
                    }
                }
            }
            pending.add(new Pending(eventId, orderId, confirmation));
        }
        long deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(confirmTimeoutMs);
        for (var item : pending) {
            try {
                var metadata = item.confirmation().get(Math.max(0, deadline - System.nanoTime()), TimeUnit.NANOSECONDS).getRecordMetadata();
                jdbc.update("UPDATE order_stream_outbox SET published_at=CURRENT_TIMESTAMP(6),attempts=attempts+1,last_error_code=NULL WHERE event_id=?",
                        item.eventId());
                log.info("PUBLISH_CONFIRMED eventId={} orderId={} topic={} partition={} offset={}",
                        item.eventId(), item.orderId(), metadata.topic(), metadata.partition(), metadata.offset());
            } catch (Exception failure) {
                if (failure instanceof InterruptedException) Thread.currentThread().interrupt();
                jdbc.update("UPDATE order_stream_outbox SET attempts=attempts+1,next_attempt_at=DATE_ADD(CURRENT_TIMESTAMP(6),INTERVAL 5 SECOND),"
                        + "last_error_code='KAFKA_UNCONFIRMED' WHERE event_id=?", item.eventId());
                log.warn("PUBLISH_DEFERRED eventId={} orderId={} topic={} reason=KAFKA_UNCONFIRMED", item.eventId(), item.orderId(), topic);
            }
        }
    }
}
