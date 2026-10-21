package cl.duoc.pedidos360.insights.audit;
import cl.duoc.pedidos360.insights.application.ProjectionStore;
import cl.duoc.pedidos360.insights.infrastructure.ManualProjectionConsumer;
import com.rabbitmq.client.Channel;
import java.io.IOException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.beans.factory.annotation.*;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;
@Component
public class AuditListener extends ManualProjectionConsumer {
    public AuditListener(@Qualifier("auditStore") ProjectionStore store,JsonMapper json,
        @Value("${pedidos.insights.max-attempts:3}") int attempts,@Value("${pedidos.insights.retry-delay-ms:1000}") long delay) {
        super(store,json,"audit",attempts,delay);
    }
    @Override @RabbitListener(id="audit-orders",queues="${pedidos.messaging.insights.audit-queue}",ackMode="MANUAL")
    public void receive(Message message,Channel channel) throws IOException { super.receive(message,channel); }
}
