package cl.duoc.pedidos360.orders;

import java.time.Duration;
import java.util.*;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.testcontainers.kafka.ConfluentKafkaContainer;
import org.testcontainers.utility.DockerImageName;

/** Ephemeral single-broker Kafka (same Confluent 7.9.10 image as Compose), named and labelled Pedidos360. */
final class TestKafka implements AutoCloseable {
    private final String suffix = UUID.randomUUID().toString().substring(0, 8);
    private final ConfluentKafkaContainer kafka = new ConfluentKafkaContainer(DockerImageName
            .parse("confluentinc/cp-kafka:7.9.10@sha256:07c3d60362e67c296f7f34b690b1240e5ecdcde4a84f5e73cab320fb4041f58c")
            .asCompatibleSubstituteFor("confluentinc/cp-kafka"))
            .withLabel("Project", "Pedidos360").withLabel("Purpose", "test")
            .withEnv("KAFKA_HEAP_OPTS", "-Xms256m -Xmx384m")
            .withCreateContainerCmdModifier(cmd -> {
                cmd.withName("pedidos360-test-kafka-orders-" + suffix);
                cmd.getHostConfig().withMemory(768L * 1024 * 1024);
            });

    TestKafka() { kafka.start(); }

    String bootstrap() { return kafka.getBootstrapServers(); }

    /** Topic declarations come from pedidos-kafka.properties; only the replication suits one broker. */
    void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.kafka.bootstrap-servers", this::bootstrap);
        registry.add("pedidos.kafka.topics.replicas", () -> "1");
        registry.add("pedidos.kafka.topics.min-insync-replicas", () -> "1");
    }

    List<ConsumerRecord<String, String>> read(String topic, int expected, Duration timeout) {
        var config = Map.<String, Object>of(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrap(),
                ConsumerConfig.GROUP_ID_CONFIG, "pedidos360-test-reader-" + UUID.randomUUID(),
                ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        var result = new ArrayList<ConsumerRecord<String, String>>();
        try (var consumer = new KafkaConsumer<>(config, new StringDeserializer(), new StringDeserializer())) {
            consumer.subscribe(List.of(topic));
            long deadline = System.nanoTime() + timeout.toNanos();
            while (result.size() < expected && System.nanoTime() < deadline) consumer.poll(Duration.ofMillis(250)).forEach(result::add);
        }
        return result;
    }

    @Override public void close() { kafka.stop(); }
}
