package cl.duoc.pedidos360.orders.infrastructure.streaming;

import cl.duoc.pedidos360.kafka.OrderRegisteredStreamV1;
import cl.duoc.pedidos360.orders.application.OrderEventRecorder;
import cl.duoc.pedidos360.orders.domain.Order;
import java.util.UUID;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;

/**
 * Inserts OrderRegisteredStreamV1 into order_stream_outbox inside the order's transaction.
 * Never contacts Kafka; a rollback leaves no orphan event. Excludes the owner's identity.
 */
@Component
@ConditionalOnProperty(name = "pedidos.kafka.enabled", havingValue = "true")
public class StreamOutboxRecorder implements OrderEventRecorder {
    private final JdbcTemplate jdbc;
    private final JsonMapper json;

    public StreamOutboxRecorder(JdbcTemplate jdbc, JsonMapper json) { this.jdbc = jdbc; this.json = json; }

    static OrderRegisteredStreamV1 event(UUID eventId, Order order) {
        var items = order.items().stream().map(item -> new OrderRegisteredStreamV1.Item(item.productId(), item.productName(),
                item.quantity(), item.unitPrice().amount(), item.subtotal().amount())).toList();
        var total = order.total();
        return new OrderRegisteredStreamV1(1, eventId, order.id(), order.owner().tenant(), order.createdAt(),
                total.currency(), total.amount(), items.size(), items);
    }

    @Override public void record(Order order) {
        var event = event(UUID.randomUUID(), order);
        jdbc.update("INSERT INTO order_stream_outbox(event_id,order_id,payload) VALUES (?,?,?)",
                event.eventId().toString(), order.id().toString(), json.writeValueAsString(event));
    }
}
