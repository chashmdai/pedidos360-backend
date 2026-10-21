package cl.duoc.pedidos360.catalog.infrastructure.persistence;
import jakarta.persistence.*;
import java.math.BigDecimal;
@Entity
@Table(name = "products")
public class ProductEntity {
    @Id @Column(length=36) String id;
    @Column(nullable=false,length=120) String name;
    @Column(nullable=false,length=500) String description;
    @Column(nullable=false,precision=19,scale=2) BigDecimal price;
    @Column(nullable=false,length=3) String currency;
    @Column(nullable=false) int stock;
    @Column(nullable=false) boolean active;
    protected ProductEntity() {}
}
