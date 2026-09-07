package cl.duoc.pedidos360.orders.domain;
import java.time.Instant;
import java.util.*;
public record Order(UUID id, OwnerId owner, List<OrderItem> items, Instant createdAt, Status status) {
    public enum Status { REGISTERED }
    public Order {
        Objects.requireNonNull(id); Objects.requireNonNull(owner); Objects.requireNonNull(createdAt); Objects.requireNonNull(status);
        if (items == null || items.isEmpty() || items.size() > 50) throw new IllegalArgumentException("El pedido requiere entre 1 y 50 líneas.");
        items = List.copyOf(items);
        if (items.stream().map(OrderItem::productId).distinct().count() != items.size())
            throw new IllegalArgumentException("Un producto no puede aparecer en más de una línea.");
        var sum = new Money(java.math.BigDecimal.ZERO, items.getFirst().unitPrice().currency());
        for (var item : items) sum = sum.add(item.subtotal());
    }
    public Money total() {
        return items.stream().map(OrderItem::subtotal).reduce(Money::add).orElseThrow();
    }
}
