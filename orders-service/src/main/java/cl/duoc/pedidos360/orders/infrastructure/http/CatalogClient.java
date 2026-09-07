package cl.duoc.pedidos360.orders.infrastructure.http;
import cl.duoc.pedidos360.orders.application.ProductLookup;
import cl.duoc.pedidos360.orders.domain.Money;
import java.math.BigDecimal;
import java.util.*;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.client.*;
public class CatalogClient implements ProductLookup {
    private final RestClient client;
    public CatalogClient(RestClient client) { this.client=client; }
    public ProductSnapshot get(UUID id) {
        var authentication=(JwtAuthenticationToken)SecurityContextHolder.getContext().getAuthentication();
        try {
            var response=client.get().uri("/api/v1/productos/{id}",id).headers(headers -> headers.setBearerAuth(authentication.getToken().getTokenValue()))
                .retrieve().body(ProductResponse.class);
            if (response==null) throw new RestClientException("Empty Catalog response");
            return new ProductSnapshot(response.id(),response.nombre(),new Money(response.precio(),response.moneda()),response.disponible());
        } catch (HttpClientErrorException.NotFound exception) { throw new NoSuchElementException(); }
    }
    record ProductResponse(UUID id,String nombre,BigDecimal precio,String moneda,boolean disponible) {}
}
