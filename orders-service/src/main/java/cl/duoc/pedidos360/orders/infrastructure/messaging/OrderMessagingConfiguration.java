package cl.duoc.pedidos360.orders.infrastructure.messaging;
import cl.duoc.pedidos360.messaging.MessagingConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.*;
import org.springframework.scheduling.annotation.EnableScheduling;
@Configuration(proxyBeanMethods=false)
@ConditionalOnProperty(name="pedidos.messaging.enabled", havingValue="true")
@EnableScheduling
@Import(MessagingConfiguration.class)
public class OrderMessagingConfiguration {}
