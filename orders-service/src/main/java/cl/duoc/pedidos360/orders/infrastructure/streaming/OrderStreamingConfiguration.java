package cl.duoc.pedidos360.orders.infrastructure.streaming;

import cl.duoc.pedidos360.kafka.KafkaSupportConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.*;
import org.springframework.scheduling.annotation.EnableScheduling;

/** EP5 Kafka streaming, enabled by property like the RabbitMQ messaging (pedidos.messaging.enabled). */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "pedidos.kafka.enabled", havingValue = "true")
@EnableScheduling
@Import(KafkaSupportConfiguration.class)
public class OrderStreamingConfiguration {}
