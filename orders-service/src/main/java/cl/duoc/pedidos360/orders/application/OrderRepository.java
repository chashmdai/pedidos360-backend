package cl.duoc.pedidos360.orders.application;
import cl.duoc.pedidos360.orders.domain.*;
import java.util.*;
public interface OrderRepository {
    Order save(Order order);
    List<Order> findByTenant(String tenant);
    List<Order> findByOwner(OwnerId owner);
    Optional<Order> findByIdAndOwner(UUID id, OwnerId owner);
}
