package cl.duoc.pedidos360.sales.infrastructure.streaming;

import cl.duoc.pedidos360.kafka.KafkaTopicProperties;
import cl.duoc.pedidos360.sales.application.MetricPublisher;
import cl.duoc.pedidos360.sales.domain.DailyProductSales;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

/** Publishes ProductSalesMetricV1 (key = metricKey) with the reliable producer of table 10 and waits for acks=all. */
@Component
public class KafkaMetricPublisher implements MetricPublisher {
    private static final Logger log = LoggerFactory.getLogger(KafkaMetricPublisher.class);
    private final KafkaTemplate<String, Object> kafka;
    private final String topic;
    private final long confirmTimeoutMs;

    public KafkaMetricPublisher(KafkaTemplate<String, Object> kafka, KafkaTopicProperties topics,
                                @Value("${pedidos.streams.metrics.confirm-timeout-ms:35000}") long confirmTimeoutMs) {
        this.kafka = kafka; this.topic = topics.productMetrics(); this.confirmTimeoutMs = confirmTimeoutMs;
    }

    @Override public void publish(List<DailyProductSales> states) {
        var sends = new ArrayList<CompletableFuture<?>>(states.size());
        for (var state : states) sends.add(kafka.send(topic, state.key().metricKey(), StreamMapping.metric(state)));
        long deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(confirmTimeoutMs);
        try {
            for (int i = 0; i < sends.size(); i++) {
                var metadata = ((org.springframework.kafka.support.SendResult<?, ?>) sends.get(i)
                        .get(Math.max(0, deadline - System.nanoTime()), TimeUnit.NANOSECONDS)).getRecordMetadata();
                var state = states.get(i);
                log.info("METRIC_PUBLISHED metricKey={} version={} lastEventId={} topic={} partition={} offset={}",
                        state.key().metricKey(), state.version(), state.lastEventId(), metadata.topic(), metadata.partition(), metadata.offset());
            }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted while waiting for metric confirmation", interrupted);
        } catch (Exception unconfirmed) {
            throw new IllegalStateException("Metric publication not confirmed", unconfirmed);
        }
    }
}
