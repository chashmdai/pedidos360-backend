package cl.duoc.pedidos360.kafka;

import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.common.config.TopicConfig;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.*;
import org.springframework.kafka.config.TopicBuilder;

/**
 * Declarative, reproducible topic definitions. KafkaAdmin creates missing topics at startup and
 * never alters existing ones. Imported explicitly by each participating service.
 */
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:pedidos-kafka.properties")
@EnableConfigurationProperties(KafkaTopicProperties.class)
public class KafkaSupportConfiguration {

    @Bean NewTopic ordersRegisteredTopic(KafkaTopicProperties t) {
        return common(TopicBuilder.name(t.ordersRegistered()), t)
                .config(TopicConfig.CLEANUP_POLICY_CONFIG, t.ordersCleanupPolicy())
                .config(TopicConfig.RETENTION_MS_CONFIG, Long.toString(t.ordersRetentionMs()))
                .config(TopicConfig.SEGMENT_MS_CONFIG, Long.toString(t.ordersSegmentMs()))
                .build();
    }

    @Bean NewTopic productMetricsTopic(KafkaTopicProperties t) {
        return common(TopicBuilder.name(t.productMetrics()), t)
                .config(TopicConfig.CLEANUP_POLICY_CONFIG, t.metricsCleanupPolicy())
                .config(TopicConfig.SEGMENT_MS_CONFIG, Long.toString(t.metricsSegmentMs()))
                .config(TopicConfig.MIN_CLEANABLE_DIRTY_RATIO_CONFIG, Double.toString(t.metricsMinCleanableDirtyRatio()))
                .config(TopicConfig.DELETE_RETENTION_MS_CONFIG, Long.toString(t.metricsDeleteRetentionMs()))
                .build();
    }

    @Bean NewTopic ordersRegisteredDltTopic(KafkaTopicProperties t) { return dlt(t.ordersRegisteredDlt(), t); }

    @Bean NewTopic productMetricsDltTopic(KafkaTopicProperties t) { return dlt(t.productMetricsDlt(), t); }

    // Same partition count as the source topic, so a failed record keeps its partition.
    private static NewTopic dlt(String name, KafkaTopicProperties t) {
        return common(TopicBuilder.name(name), t)
                .config(TopicConfig.CLEANUP_POLICY_CONFIG, t.dltCleanupPolicy())
                .config(TopicConfig.RETENTION_MS_CONFIG, Long.toString(t.dltRetentionMs()))
                .config(TopicConfig.SEGMENT_MS_CONFIG, Long.toString(t.dltSegmentMs()))
                .build();
    }

    private static TopicBuilder common(TopicBuilder builder, KafkaTopicProperties t) {
        return builder.partitions(t.partitions()).replicas(t.replicas())
                .config(TopicConfig.MIN_IN_SYNC_REPLICAS_CONFIG, Integer.toString(t.minInsyncReplicas()))
                .config(TopicConfig.MAX_MESSAGE_BYTES_CONFIG, Integer.toString(t.maxMessageBytes()));
    }
}
