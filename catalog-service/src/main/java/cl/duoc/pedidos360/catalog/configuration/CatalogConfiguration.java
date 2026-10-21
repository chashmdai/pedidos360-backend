package cl.duoc.pedidos360.catalog.configuration;
import cl.duoc.pedidos360.catalog.application.*;
import org.springframework.context.annotation.*;
@Configuration
public class CatalogConfiguration {
    @Bean CatalogService catalogService(ProductRepository repository) { return new CatalogService(repository); }
}
