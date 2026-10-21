package cl.duoc.pedidos360.orders.infrastructure.persistence;
import jakarta.persistence.*;
import java.math.BigDecimal;
@Entity @Table(name="order_items")
public class OrderLineEntity {
    @Id @GeneratedValue(strategy=GenerationType.IDENTITY) Long id;
    @ManyToOne(fetch=FetchType.LAZY,optional=false) @JoinColumn(name="order_id",nullable=false) OrderEntity order;
    @Column(nullable=false,length=36) String productId;
    @Column(nullable=false,length=120) String productName;
    @Column(nullable=false,precision=19,scale=2) BigDecimal unitPrice;
    @Column(nullable=false,length=3) String currency;
    @Column(nullable=false) int quantity;
    protected OrderLineEntity() {}
}
