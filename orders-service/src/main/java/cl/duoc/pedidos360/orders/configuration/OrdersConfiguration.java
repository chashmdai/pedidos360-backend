package cl.duoc.pedidos360.orders.configuration;
import cl.duoc.pedidos360.orders.application.*;
import cl.duoc.pedidos360.orders.infrastructure.http.CatalogClient;
import java.net.http.HttpClient;
import java.time.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.*;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;
@Configuration
public class OrdersConfiguration {
    @Bean ProductLookup productLookup(@Value("${pedidos.catalog-url}") String url) {
        var factory=new JdkClientHttpRequestFactory(HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).followRedirects(HttpClient.Redirect.NEVER).build());
        factory.setReadTimeout(Duration.ofSeconds(5));
        return new CatalogClient(RestClient.builder().baseUrl(url).requestFactory(factory).build());
    }
    @Bean OrderService orderService(OrderRepository repository,ProductLookup products) { return new OrderService(repository,products,Clock.systemUTC()); }
}
