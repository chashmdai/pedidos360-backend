package cl.duoc.pedidos360.catalog.application;
import cl.duoc.pedidos360.catalog.domain.Product;
import java.util.*;
public class CatalogService {
    private final ProductRepository products;
    public CatalogService(ProductRepository products) { this.products = products; }
    public List<Product> list() { return products.findAll(); }
    public Product get(UUID id) { return products.findById(id).orElseThrow(NoSuchElementException::new); }
}
