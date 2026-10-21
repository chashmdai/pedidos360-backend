package cl.duoc.pedidos360.orders.infrastructure.persistence;
import cl.duoc.pedidos360.orders.application.OrderRepository;
import cl.duoc.pedidos360.orders.domain.*;
import java.util.*;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;
@Repository
@Transactional(readOnly=true)
public class OrderPersistence implements OrderRepository {
    private final JpaOrders repository;
    public OrderPersistence(JpaOrders repository) { this.repository=repository; }
    @Transactional
    public Order save(Order order) {
        var entity=new OrderEntity();
        entity.id=order.id().toString(); entity.ownerTenant=order.owner().tenant(); entity.ownerSubject=order.owner().subject();
        // MySQL DATETIME(6) persists microseconds; return the same timestamp on POST and GET.
        entity.status=order.status().name(); entity.createdAt=order.createdAt().truncatedTo(java.time.temporal.ChronoUnit.MICROS);
        for (var item:order.items()) {
            var line=new OrderLineEntity(); line.order=entity; line.productId=item.productId().toString(); line.productName=item.productName();
            line.unitPrice=item.unitPrice().amount(); line.currency=item.unitPrice().currency(); line.quantity=item.quantity(); entity.items.add(line);
        }
        return map(repository.saveAndFlush(entity));
    }
    public List<Order> findByTenant(String tenant) {
        return repository.findByOwnerTenantOrderByCreatedAtDesc(tenant).stream().map(this::map).toList();
    }
    public List<Order> findByOwner(OwnerId owner) {
        return repository.findByOwnerTenantAndOwnerSubjectOrderByCreatedAtDesc(owner.tenant(),owner.subject()).stream().map(this::map).toList();
    }
    public Optional<Order> findByIdAndOwner(UUID id, OwnerId owner) {
        return repository.findByIdAndOwnerTenantAndOwnerSubject(id.toString(),owner.tenant(),owner.subject()).map(this::map);
    }
    private Order map(OrderEntity entity) {
        var items=entity.items.stream().map(line -> new OrderItem(UUID.fromString(line.productId),line.productName,new Money(line.unitPrice,line.currency),line.quantity)).toList();
        return new Order(UUID.fromString(entity.id),new OwnerId(entity.ownerTenant,entity.ownerSubject),items,entity.createdAt,Order.Status.valueOf(entity.status));
    }
}
