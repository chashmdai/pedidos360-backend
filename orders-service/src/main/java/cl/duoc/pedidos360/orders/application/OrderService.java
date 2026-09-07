package cl.duoc.pedidos360.orders.application;
import cl.duoc.pedidos360.orders.domain.*;
import java.time.Clock;
import java.util.*;
public class OrderService {
    private final OrderRepository orders;
    private final ProductLookup products;
    private final Clock clock;
    public OrderService(OrderRepository orders, ProductLookup products, Clock clock) { this.orders=orders; this.products=products; this.clock=clock; }
    public record RequestedItem(UUID productId, int quantity) {
        public RequestedItem {
            Objects.requireNonNull(productId);
            if (quantity < 1 || quantity > 1000) throw new IllegalArgumentException("La cantidad debe estar entre 1 y 1000.");
        }
    }
    public Order create(OwnerId owner, List<RequestedItem> requested) {
        if (requested == null || requested.isEmpty() || requested.size() > 50) throw new IllegalArgumentException("El pedido requiere entre 1 y 50 líneas.");
        if (requested.stream().map(RequestedItem::productId).distinct().count()!=requested.size())
            throw new IllegalArgumentException("No repitas productos en el pedido.");
        var items = requested.stream().map(item -> {
            var product=products.get(item.productId());
            if (!product.available()) throw new IllegalArgumentException("El producto no está disponible.");
            return new OrderItem(product.id(),product.name(),product.price(),item.quantity());
        }).toList();
        return orders.save(new Order(UUID.randomUUID(),owner,items,clock.instant(),Order.Status.REGISTERED));
    }
    public List<Order> listForAdministration(String tenant) { return orders.findByTenant(tenant); }
    public List<Order> list(OwnerId owner) { return orders.findByOwner(owner); }
    public Order get(UUID id, OwnerId owner) { return orders.findByIdAndOwner(id,owner).orElseThrow(NoSuchElementException::new); }
}
