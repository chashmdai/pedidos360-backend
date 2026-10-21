package cl.duoc.pedidos360.messaging;

import org.springframework.amqp.core.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.*;
import org.springframework.context.annotation.*;

/** EP4 routes are additive; the original direct receipt route is unchanged. */
@Configuration(proxyBeanMethods=false)
@ConditionalOnProperty(name="pedidos.messaging.ep4-enabled",havingValue="true")
@EnableConfigurationProperties(InsightsTopology.Names.class)
public class InsightsTopology {
    @ConfigurationProperties("pedidos.messaging.insights")
    public record Names(String topicExchange, String auditQueue, String auditPattern,
        String auditDeadExchange, String auditDeadQueue, String auditDeadKey,
        String salesQueue, String salesPattern, String salesDeadExchange,
        String salesDeadQueue, String salesDeadKey) {}
    @Bean TopicExchange insightsEvents(Names n) { return new TopicExchange(n.topicExchange(),true,false); }
    // One outbox publication reaches the legacy direct queue and the two topic subscribers.
    @Bean Binding insightsFromOrders(Names n,MessagingProperties p) {
        return new Binding(n.topicExchange(),Binding.DestinationType.EXCHANGE,p.exchange(),p.routingKey(),null);
    }
    @Bean Queue auditQueue(Names n) { return QueueBuilder.durable(n.auditQueue()).deadLetterExchange(n.auditDeadExchange()).deadLetterRoutingKey(n.auditDeadKey()).build(); }
    @Bean DirectExchange auditErrors(Names n) { return new DirectExchange(n.auditDeadExchange(),true,false); }
    @Bean Queue auditDeadQueue(Names n) { return QueueBuilder.durable(n.auditDeadQueue()).build(); }
    @Bean Binding auditOrders(Names n) { return new Binding(n.auditQueue(),Binding.DestinationType.QUEUE,n.topicExchange(),n.auditPattern(),null); }
    @Bean Binding auditFailures(Names n) { return new Binding(n.auditDeadQueue(),Binding.DestinationType.QUEUE,n.auditDeadExchange(),n.auditDeadKey(),null); }
    @Bean Queue salesQueue(Names n) { return QueueBuilder.durable(n.salesQueue()).deadLetterExchange(n.salesDeadExchange()).deadLetterRoutingKey(n.salesDeadKey()).build(); }
    @Bean DirectExchange salesErrors(Names n) { return new DirectExchange(n.salesDeadExchange(),true,false); }
    @Bean Queue salesDeadQueue(Names n) { return QueueBuilder.durable(n.salesDeadQueue()).build(); }
    @Bean Binding salesOrders(Names n) { return new Binding(n.salesQueue(),Binding.DestinationType.QUEUE,n.topicExchange(),n.salesPattern(),null); }
    @Bean Binding salesFailures(Names n) { return new Binding(n.salesDeadQueue(),Binding.DestinationType.QUEUE,n.salesDeadExchange(),n.salesDeadKey(),null); }
}
