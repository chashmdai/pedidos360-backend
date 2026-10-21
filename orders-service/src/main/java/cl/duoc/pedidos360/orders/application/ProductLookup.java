package cl.duoc.pedidos360.orders.application;
import cl.duoc.pedidos360.orders.domain.Money;
import java.util.UUID;
public interface ProductLookup {
    ProductSnapshot get(UUID id);
    record ProductSnapshot(UUID id, String name, Money price, boolean available) {}
}
