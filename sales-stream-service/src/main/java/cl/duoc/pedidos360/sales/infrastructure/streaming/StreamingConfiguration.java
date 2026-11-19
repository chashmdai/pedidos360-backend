package cl.duoc.pedidos360.sales.infrastructure.streaming;

import cl.duoc.pedidos360.kafka.KafkaSupportConfiguration;
import cl.duoc.pedidos360.kafka.KafkaTopicProperties;
import cl.duoc.pedidos360.kafka.OrderRegisteredStreamV1;
import cl.duoc.pedidos360.kafka.ProductSalesMetricV1;
import cl.duoc.pedidos360.kafka.StreamContractException;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.ByteArraySerializer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.kafka.autoconfigure.KafkaProperties;
import org.springframework.context.annotation.*;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.*;
import org.springframework.kafka.listener.ContainerProperties.AckMode;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.support.serializer.ErrorHandlingDeserializer;
import org.springframework.kafka.support.serializer.JacksonJsonDeserializer;
import org.springframework.kafka.support.ExponentialBackOffWithMaxRetries;

/**
 * Consumers of report tables 11 and 12. Common consumer properties come from spring.kafka.consumer.*
 * (application.properties); each factory fixes its value type, group, start position and concurrency.
 */
@Configuration(proxyBeanMethods = false)
@Import(KafkaSupportConfiguration.class)
public class StreamingConfiguration {
    public static final String AGGREGATOR_FACTORY = "aggregatorContainerFactory";
    public static final String MONITOR_FACTORY = "monitorContainerFactory";
    public static final String DASHBOARD_FACTORY = "dashboardContainerFactory";

    /** Table 12: ErrorHandlingDeserializer over a JSON deserializer with a fixed target type and no type headers. */
    static Map<String, Object> consumerProperties(KafkaProperties kafka, Class<?> type, String group, String offsetReset) {
        var props = new HashMap<>(kafka.buildConsumerProperties());
        props.put(ConsumerConfig.GROUP_ID_CONFIG, group);
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, offsetReset);
        props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, ErrorHandlingDeserializer.class);
        props.put(ErrorHandlingDeserializer.VALUE_DESERIALIZER_CLASS, JacksonJsonDeserializer.class);
        props.put(JacksonJsonDeserializer.VALUE_DEFAULT_TYPE, type.getName());
        props.put(JacksonJsonDeserializer.USE_TYPE_INFO_HEADERS, false);
        props.put(JacksonJsonDeserializer.TRUSTED_PACKAGES, type.getPackageName());
        return props;
    }

    /** DLT: <topic>.DLT in the SAME partition; raw bytes for undeserializable records, JSON otherwise. */
    static DefaultErrorHandler errorHandler(KafkaOperations<?, ?> json, KafkaOperations<?, ?> bytes, KafkaTopicProperties topics,
                                            String group, long initialMs, double multiplier, int maxRetries) {
        var templates = new LinkedHashMap<Class<?>, KafkaOperations<?, ?>>();
        templates.put(byte[].class, bytes);
        templates.put(Object.class, json);
        var recoverer = new DeadLetterPublishingRecoverer(templates,
                (record, error) -> new TopicPartition(record.topic() + topics.dltSuffix(), record.partition()));
        // Table 13: transient errors -> exponential backoff 1 s, then 2 s: three attempts in total.
        var backOff = new ExponentialBackOffWithMaxRetries(maxRetries);   // retries after the first attempt
        backOff.setInitialInterval(initialMs);
        backOff.setMultiplier(multiplier);
        var handler = new DefaultErrorHandler(recoverer, backOff);
        // Contract and deserialization errors go to the DLT immediately (DeserializationException is already not retryable).
        handler.addNotRetryableExceptions(StreamContractException.class);
        handler.setRetryListeners(new ConsumptionLog(group, maxRetries));
        return handler;
    }

    /**
     * Raw-bytes producer for undeserializable records. Wrapped in its own type so that Spring Boot's
     * auto-configured KafkaTemplate/ProducerFactory (JSON, table 10) are still created.
     */
    public static final class DeadLetterBytes implements org.springframework.beans.factory.DisposableBean {
        private final DefaultKafkaProducerFactory<String, byte[]> factory;
        final KafkaTemplate<String, byte[]> template;

        DeadLetterBytes(Map<String, Object> props) { factory = new DefaultKafkaProducerFactory<>(props); template = new KafkaTemplate<>(factory); }

        @Override public void destroy() { factory.destroy(); }
    }

    @Bean DeadLetterBytes deadLetterBytes(KafkaProperties kafka) {
        var props = new HashMap<>(kafka.buildProducerProperties());
        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, ByteArraySerializer.class);
        props.put(ProducerConfig.CLIENT_ID_CONFIG, props.getOrDefault(ProducerConfig.CLIENT_ID_CONFIG, "sales-stream-service") + "-dlt");
        return new DeadLetterBytes(props);
    }

    private static <T> ConcurrentKafkaListenerContainerFactory<String, T> factory(ConsumerFactory<String, T> consumers, int concurrency,
            DefaultErrorHandler errors, boolean autoStartup) {
        var factory = new ConcurrentKafkaListenerContainerFactory<String, T>();
        factory.setConsumerFactory(consumers);
        factory.setConcurrency(concurrency);
        factory.setCommonErrorHandler(errors);
        factory.setAutoStartup(autoStartup);
        factory.getContainerProperties().setAckMode(AckMode.RECORD);    // offset committed after each processed record
        factory.getContainerProperties().setDeliveryAttemptHeader(true);
        return factory;
    }

    record Retry(long initialMs, double multiplier, int maxRetries) {}

    @Bean Retry consumerRetry(@Value("${pedidos.streams.retry.initial-interval-ms:1000}") long initialMs,
                              @Value("${pedidos.streams.retry.multiplier:2.0}") double multiplier,
                              @Value("${pedidos.streams.retry.max-retries:2}") int maxRetries) {
        return new Retry(initialMs, multiplier, maxRetries);
    }

    @Bean(AGGREGATOR_FACTORY) ConcurrentKafkaListenerContainerFactory<String, OrderRegisteredStreamV1> aggregatorContainerFactory(
            KafkaProperties kafka, KafkaTopicProperties topics, KafkaTemplate<?, ?> json, DeadLetterBytes deadLetterBytes, Retry retry,
            @Value("${pedidos.kafka.groups.sales-aggregator}") String group,
            @Value("${pedidos.streams.consumers.sales-aggregator.concurrency:3}") int concurrency,
            @Value("${pedidos.streams.listeners.auto-startup:true}") boolean autoStartup) {
        var consumers = new DefaultKafkaConsumerFactory<String, OrderRegisteredStreamV1>(consumerProperties(kafka, OrderRegisteredStreamV1.class, group, "earliest"));
        return factory(consumers, concurrency, errorHandler(json, deadLetterBytes.template, topics, group, retry.initialMs(), retry.multiplier(), retry.maxRetries()), autoStartup);
    }

    @Bean(MONITOR_FACTORY) ConcurrentKafkaListenerContainerFactory<String, OrderRegisteredStreamV1> monitorContainerFactory(
            KafkaProperties kafka, KafkaTopicProperties topics, KafkaTemplate<?, ?> json, DeadLetterBytes deadLetterBytes, Retry retry,
            @Value("${pedidos.kafka.groups.order-monitor}") String group,
            @Value("${pedidos.streams.consumers.order-monitor.concurrency:1}") int concurrency,
            @Value("${pedidos.streams.listeners.auto-startup:true}") boolean autoStartup) {
        var consumers = new DefaultKafkaConsumerFactory<String, OrderRegisteredStreamV1>(consumerProperties(kafka, OrderRegisteredStreamV1.class, group, "latest"));
        return factory(consumers, concurrency, errorHandler(json, deadLetterBytes.template, topics, group, retry.initialMs(), retry.multiplier(), retry.maxRetries()), autoStartup);
    }

    @Bean(DASHBOARD_FACTORY) ConcurrentKafkaListenerContainerFactory<String, ProductSalesMetricV1> dashboardContainerFactory(
            KafkaProperties kafka, KafkaTopicProperties topics, KafkaTemplate<?, ?> json, DeadLetterBytes deadLetterBytes, Retry retry,
            @Value("${pedidos.kafka.groups.sales-dashboard}") String group,
            @Value("${pedidos.streams.consumers.sales-dashboard.concurrency:1}") int concurrency,
            @Value("${pedidos.streams.listeners.auto-startup:true}") boolean autoStartup) {
        // The dashboard seeks to the beginning on every assignment (ConsumerSeekAware); earliest only covers a brand-new group.
        var consumers = new DefaultKafkaConsumerFactory<String, ProductSalesMetricV1>(consumerProperties(kafka, ProductSalesMetricV1.class, group, "earliest"));
        return factory(consumers, concurrency, errorHandler(json, deadLetterBytes.template, topics, group, retry.initialMs(), retry.multiplier(), retry.maxRetries()), autoStartup);
    }
}
