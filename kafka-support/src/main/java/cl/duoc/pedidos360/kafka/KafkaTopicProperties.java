package cl.duoc.pedidos360.kafka;

import org.springframework.boot.context.properties.ConfigurationProperties;

/** Topic names and parameters from pedidos-kafka.properties (report tables 6 and 7). */
@ConfigurationProperties("pedidos.kafka.topics")
public record KafkaTopicProperties(
        String ordersRegistered, String productMetrics, String dltSuffix, int partitions, int replicas,
        int minInsyncReplicas, int maxMessageBytes,
        String ordersCleanupPolicy, long ordersRetentionMs, long ordersSegmentMs,
        String metricsCleanupPolicy, long metricsSegmentMs, double metricsMinCleanableDirtyRatio, long metricsDeleteRetentionMs,
        String dltCleanupPolicy, long dltRetentionMs, long dltSegmentMs) {

    public String ordersRegisteredDlt() { return ordersRegistered + dltSuffix; }

    public String productMetricsDlt() { return productMetrics + dltSuffix; }
}
