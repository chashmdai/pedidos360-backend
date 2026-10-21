package cl.duoc.pedidos360.messaging;

import org.springframework.amqp.core.*;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.*;

@Configuration(proxyBeanMethods=false)
@PropertySource("classpath:pedidos-rabbit.properties")
@EnableConfigurationProperties(MessagingProperties.class)
public class MessagingConfiguration {
    @Bean DirectExchange orderEvents(MessagingProperties p) { return new DirectExchange(p.exchange(), true, false); }
    @Bean DirectExchange receiptErrors(MessagingProperties p) { return new DirectExchange(p.deadExchange(), true, false); }
    @Bean Queue receiptQueue(MessagingProperties p) {
        return QueueBuilder.durable(p.queue()).deadLetterExchange(p.deadExchange())
                .deadLetterRoutingKey(p.deadRoutingKey()).build();
    }
    @Bean Queue receiptDeadQueue(MessagingProperties p) { return QueueBuilder.durable(p.deadQueue()).build(); }
    @Bean Binding orderReceiptBinding(MessagingProperties p) {
        return new Binding(p.queue(), Binding.DestinationType.QUEUE, p.exchange(), p.routingKey(), null);
    }
    @Bean Binding receiptDeadBinding(MessagingProperties p) {
        return new Binding(p.deadQueue(), Binding.DestinationType.QUEUE, p.deadExchange(), p.deadRoutingKey(), null);
    }
}
