package cl.duoc.pedidos360.catalog.application;
import cl.duoc.pedidos360.catalog.domain.Product;
import java.util.*;
public interface ProductRepository {
    List<Product> findAll();
    Optional<Product> findById(UUID id);
}
