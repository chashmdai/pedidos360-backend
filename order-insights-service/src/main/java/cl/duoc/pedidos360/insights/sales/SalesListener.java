package cl.duoc.pedidos360.insights.sales;
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
public class SalesListener extends ManualProjectionConsumer {
    public SalesListener(@Qualifier("salesStore") ProjectionStore store,JsonMapper json,
        @Value("${pedidos.insights.max-attempts:3}") int attempts,@Value("${pedidos.insights.retry-delay-ms:1000}") long delay) {
        super(store,json,"sales",attempts,delay);
    }
    @Override @RabbitListener(id="sales-orders",queues="${pedidos.messaging.insights.sales-queue}",ackMode="MANUAL")
    public void receive(Message message,Channel channel) throws IOException { super.receive(message,channel); }
}
