package cl.duoc.pedidos360.catalog.infrastructure.persistence;
import cl.duoc.pedidos360.catalog.application.ProductRepository;
import cl.duoc.pedidos360.catalog.domain.Product;
import java.util.*;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Repository;
@Repository
public class ProductPersistence implements ProductRepository {
    private final JpaProducts repository;
    public ProductPersistence(JpaProducts repository) { this.repository = repository; }
    public List<Product> findAll() { return repository.findAll(Sort.by("name")).stream().map(this::map).toList(); }
    public Optional<Product> findById(UUID id) { return repository.findById(id.toString()).map(this::map); }
    private Product map(ProductEntity entity) {
        return new Product(UUID.fromString(entity.id),entity.name,entity.description,entity.price,entity.currency,entity.stock,entity.active);
    }
}
