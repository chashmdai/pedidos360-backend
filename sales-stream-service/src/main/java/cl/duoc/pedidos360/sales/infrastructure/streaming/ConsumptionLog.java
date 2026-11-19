package cl.duoc.pedidos360.sales.infrastructure.streaming;

import cl.duoc.pedidos360.kafka.OrderRegisteredStreamV1;
import cl.duoc.pedidos360.kafka.ProductSalesMetricV1;
import cl.duoc.pedidos360.kafka.StreamContractException;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.listener.RetryListener;
import org.springframework.kafka.support.serializer.DeserializationException;
import tools.jackson.databind.json.JsonMapper;

/**
 * key=value consumption logs: CONSUME_OK, CONSUME_RETRY, CONSUME_DLT, CONSUME_DUPLICATE with eventId, group,
 * topic, partition, offset, attempt and an error code. Never logs the payload or identity data.
 */
final class ConsumptionLog implements RetryListener {
    private static final Logger log = LoggerFactory.getLogger(ConsumptionLog.class);
    private static final JsonMapper JSON = new JsonMapper();
    private final String group;
    private final int maxRetries;

    ConsumptionLog(String group) { this(group, 0); }

    ConsumptionLog(String group, int maxRetries) { this.group = group; this.maxRetries = maxRetries; }

    void ok(ConsumerRecord<?, ?> record, int attempt, String result) { log.info("CONSUME_OK {} attempt={} result={}", context(record, null), attempt, result); }

    void duplicate(ConsumerRecord<?, ?> record, int attempt) { log.info("CONSUME_DUPLICATE {} attempt={} code=ALREADY_PROCESSED", context(record, null), attempt); }

    @Override public void failedDelivery(ConsumerRecord<?, ?> record, Exception error, int attempt) {
        // Also called for the final failed attempt, right before recovery: log RETRY only if another attempt follows.
        if (!permanent(error) && attempt <= maxRetries) log.warn("CONSUME_RETRY {} attempt={} code={}", context(record, error), attempt, code(error));
    }

    @Override public void recovered(ConsumerRecord<?, ?> record, Exception error) {
        log.error("CONSUME_DLT {} code={} retried={}", context(record, error), code(error), !permanent(error));
    }

    @Override public void recoveryFailed(ConsumerRecord<?, ?> record, Exception original, Exception failure) {
        log.error("CONSUME_DLT_FAILED {} code={} dltError={}", context(record, original), code(original), failure.getClass().getSimpleName());
    }

    private String context(ConsumerRecord<?, ?> record, Throwable error) {
        return "eventId=" + eventId(record, error) + " group=" + group + " topic=" + record.topic() + " partition=" + record.partition() + " offset=" + record.offset();
    }

    static boolean permanent(Throwable error) { return find(error, StreamContractException.class) != null || find(error, DeserializationException.class) != null; }

    static String code(Throwable error) {
        if (find(error, StreamContractException.class) != null) return "CONTRACT_INVALID";
        if (find(error, DeserializationException.class) != null) return "DESERIALIZATION_FAILED";
        Throwable root = error;
        while (root.getCause() != null && root.getCause() != root) root = root.getCause();
        return "TRANSIENT_" + root.getClass().getSimpleName();
    }

    /** eventId of a deserialized record, or read best-effort from the raw bytes of an undeserializable one. */
    static String eventId(ConsumerRecord<?, ?> record, Throwable error) {
        if (record.value() instanceof OrderRegisteredStreamV1 event) return event.eventId().toString();
        if (record.value() instanceof ProductSalesMetricV1 metric) return metric.lastEventId().toString();
        var failure = error == null ? null : find(error, DeserializationException.class);
        if (failure != null && failure.getData() != null) {
            try {
                var id = JSON.readTree(failure.getData()).get("eventId");
                if (id != null && id.isString() && id.asString().length() <= 36) return id.asString();
            } catch (RuntimeException malformed) { /* not JSON: no eventId available */ }
        }
        return "unknown";
    }

    private static <T extends Throwable> T find(Throwable error, Class<T> type) {
        for (Throwable t = error; t != null; t = t.getCause() == t ? null : t.getCause()) if (type.isInstance(t)) return type.cast(t);
        return null;
    }
}
