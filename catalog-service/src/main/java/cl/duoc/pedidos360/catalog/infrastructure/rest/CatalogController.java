package cl.duoc.pedidos360.catalog.infrastructure.rest;
import cl.duoc.pedidos360.catalog.application.CatalogService;
import cl.duoc.pedidos360.catalog.domain.Product;
import java.math.BigDecimal;
import java.util.*;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping("/api/v1/productos")
public class CatalogController {
    private final CatalogService catalog;
    public CatalogController(CatalogService catalog) { this.catalog = catalog; }
    @GetMapping public List<ProductResponse> list() { return catalog.list().stream().map(ProductResponse::from).toList(); }
    @GetMapping("/{id}") public ProductResponse get(@PathVariable UUID id) { return ProductResponse.from(catalog.get(id)); }
    public record ProductResponse(UUID id, String nombre, String descripcion, BigDecimal precio, String moneda, int stock, boolean disponible) {
        static ProductResponse from(Product p) { return new ProductResponse(p.id(),p.name(),p.description(),p.price(),p.currency(),p.stock(),p.active()); }
    }
}
