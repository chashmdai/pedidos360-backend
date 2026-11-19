package cl.duoc.pedidos360.kafka;

import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import org.apache.kafka.clients.admin.NewTopic;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

/** Literal check of report tables 6 (names, P/R) and 7 (per-flow parameters). */
class TopicDeclarationTest {
    final ApplicationContextRunner runner = new ApplicationContextRunner().withUserConfiguration(KafkaSupportConfiguration.class);

    @Test void topicsMatchTables6And7() {
        runner.run(context -> {
            var topics = context.getBeansOfType(NewTopic.class).values().stream()
                    .collect(java.util.stream.Collectors.toMap(NewTopic::name, t -> t));
            assertEquals(java.util.Set.of("pedidos360.orders.registered.v1", "pedidos360.sales.product-metrics.v1",
                    "pedidos360.orders.registered.v1.DLT", "pedidos360.sales.product-metrics.v1.DLT"), topics.keySet());
            topics.values().forEach(t -> {
                assertEquals(3, t.numPartitions(), t.name());
                assertEquals((short) 3, t.replicationFactor(), t.name());
            });
            assertEquals(Map.of("cleanup.policy", "delete", "retention.ms", "604800000", "min.insync.replicas", "2",
                    "segment.ms", "86400000", "max.message.bytes", "1048576"),
                    topics.get("pedidos360.orders.registered.v1").configs());
            assertEquals(Map.of("cleanup.policy", "compact", "min.insync.replicas", "2", "segment.ms", "3600000",
                    "min.cleanable.dirty.ratio", "0.1", "delete.retention.ms", "86400000", "max.message.bytes", "1048576"),
                    topics.get("pedidos360.sales.product-metrics.v1").configs());
            var dlt = Map.of("cleanup.policy", "delete", "retention.ms", "1209600000", "min.insync.replicas", "2",
                    "segment.ms", "86400000", "max.message.bytes", "1048576");
            assertEquals(dlt, topics.get("pedidos360.orders.registered.v1.DLT").configs());
            assertEquals(dlt, topics.get("pedidos360.sales.product-metrics.v1.DLT").configs());
        });
    }

    @Test void producerSettingsMatchTable10() {
        runner.run(context -> {
            var env = context.getEnvironment();
            assertEquals("127.0.0.1:19092,127.0.0.1:19093,127.0.0.1:19094", env.getProperty("spring.kafka.bootstrap-servers"));
            assertEquals("org.apache.kafka.common.serialization.StringSerializer", env.getProperty("spring.kafka.producer.key-serializer"));
            assertEquals("org.springframework.kafka.support.serializer.JacksonJsonSerializer", env.getProperty("spring.kafka.producer.value-serializer"));
            assertEquals("all", env.getProperty("spring.kafka.producer.acks"));
            assertEquals("lz4", env.getProperty("spring.kafka.producer.compression-type"));
            assertEquals("true", env.getProperty("spring.kafka.producer.properties.enable.idempotence"));
            assertEquals("5", env.getProperty("spring.kafka.producer.properties.max.in.flight.requests.per.connection"));
            assertEquals("30000", env.getProperty("spring.kafka.producer.properties.delivery.timeout.ms"));
            assertEquals("10000", env.getProperty("spring.kafka.producer.properties.request.timeout.ms"));
            assertEquals("5", env.getProperty("spring.kafka.producer.properties.linger.ms"));
            assertEquals("false", env.getProperty("spring.kafka.producer.properties.spring.json.add.type.headers"));
        });
    }
}
