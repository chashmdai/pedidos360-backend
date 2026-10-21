package cl.duoc.pedidos360.messaging;
import org.springframework.boot.context.properties.ConfigurationProperties;
@ConfigurationProperties("pedidos.messaging")
public record MessagingProperties(String exchange, String routingKey, String queue,
                                 String deadExchange, String deadRoutingKey, String deadQueue) {}
