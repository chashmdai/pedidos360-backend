package cl.duoc.pedidos360.orders.infrastructure.messaging;
import cl.duoc.pedidos360.messaging.OrderRegisteredV1;
import cl.duoc.pedidos360.orders.application.OrderEventRecorder;
import cl.duoc.pedidos360.orders.domain.Order;
import java.util.UUID;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;
@Component
@ConditionalOnProperty(name="pedidos.messaging.enabled", havingValue="true")
public class OutboxRecorder implements OrderEventRecorder {
    private final JdbcTemplate jdbc;
    private final JsonMapper json;
    public OutboxRecorder(JdbcTemplate jdbc, JsonMapper json) { this.jdbc=jdbc; this.json=json; }
    public void record(Order order) {
        var event = new OrderRegisteredV1(1, UUID.randomUUID(), order.id(), order.owner().tenant(),
                order.createdAt(), order.total().amount(), order.total().currency(), order.items().size());
        jdbc.update("INSERT INTO order_event_outbox(event_id,order_id,payload) VALUES (?,?,?)",
                event.eventId().toString(), order.id().toString(), json.writeValueAsString(event));
    }
}
