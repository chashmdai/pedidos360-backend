package cl.duoc.pedidos360.orders.infrastructure.persistence;
import jakarta.persistence.*;
import java.time.Instant;
import java.util.*;
@Entity @Table(name="purchase_orders")
public class OrderEntity {
    @Id @Column(length=36) String id;
    @Column(nullable=false,length=100) String ownerTenant;
    @Column(nullable=false,length=100) String ownerSubject;
    @Column(nullable=false,length=20) String status;
    @Column(nullable=false) Instant createdAt;
    @OneToMany(mappedBy="order",cascade=CascadeType.ALL,orphanRemoval=true)
    @OrderBy("id ASC") List<OrderLineEntity> items = new ArrayList<>();
    protected OrderEntity() {}
}
