package cl.duoc.pedidos360.kafkaadmin.configuration;

import cl.duoc.pedidos360.kafka.KafkaTopicProperties;
import java.util.HashMap;
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.kafka.autoconfigure.KafkaProperties;
import org.springframework.context.annotation.*;

/**
 * One long-lived AdminClient with bounded timeouts (a silent cluster answers 503 instead of hanging).
 * Reads topic names from pedidos-kafka.properties only to protect business topics; it declares no NewTopic.
 */
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:pedidos-kafka.properties")
@EnableConfigurationProperties(KafkaTopicProperties.class)
public class KafkaAdminConfiguration {
    @Bean(destroyMethod = "close") Admin kafkaAdminClient(KafkaProperties kafka,
            @Value("${spring.application.name}") String clientId,
            @Value("${pedidos.kafka-admin.request-timeout-ms:5000}") int requestTimeoutMs,
            @Value("${pedidos.kafka-admin.api-timeout-ms:10000}") int apiTimeoutMs) {
        var props = new HashMap<>(kafka.buildAdminProperties());
        props.put(AdminClientConfig.CLIENT_ID_CONFIG, clientId);
        props.put(AdminClientConfig.REQUEST_TIMEOUT_MS_CONFIG, requestTimeoutMs);
        props.put(AdminClientConfig.DEFAULT_API_TIMEOUT_MS_CONFIG, apiTimeoutMs);
        return Admin.create(props);
    }
}
