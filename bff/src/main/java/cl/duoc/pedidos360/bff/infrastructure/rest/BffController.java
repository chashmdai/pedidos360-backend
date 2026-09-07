package cl.duoc.pedidos360.bff.infrastructure.rest;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestClient;

@RestController
@RequestMapping("/api/v1")
public class BffController {
    private final RestClient catalog;
    private final RestClient orders;
    public BffController(@Value("${pedidos.catalog-url}") String catalogUrl,@Value("${pedidos.orders-url}") String ordersUrl) {
        this.catalog=client(catalogUrl); this.orders=client(ordersUrl);
    }
    private RestClient client(String url) {
        var factory=new JdkClientHttpRequestFactory(HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).followRedirects(HttpClient.Redirect.NEVER).build());
        factory.setReadTimeout(Duration.ofSeconds(8));
        return RestClient.builder().baseUrl(url).requestFactory(factory).build();
    }
    @GetMapping("/productos") ResponseEntity<byte[]> products(@AuthenticationPrincipal Jwt jwt) { return forward(catalog,HttpMethod.GET,"/api/v1/productos",null,jwt); }
    @GetMapping("/productos/{id}") ResponseEntity<byte[]> product(@PathVariable UUID id,@AuthenticationPrincipal Jwt jwt) { return forward(catalog,HttpMethod.GET,"/api/v1/productos/"+id,null,jwt); }
    @GetMapping("/pedidos") ResponseEntity<byte[]> orders(@AuthenticationPrincipal Jwt jwt) { return forward(orders,HttpMethod.GET,"/api/v1/pedidos",null,jwt); }
    @GetMapping("/pedidos/{id}") ResponseEntity<byte[]> order(@PathVariable UUID id,@AuthenticationPrincipal Jwt jwt) { return forward(orders,HttpMethod.GET,"/api/v1/pedidos/"+id,null,jwt); }
    @GetMapping("/admin/pedidos") ResponseEntity<byte[]> administration(@AuthenticationPrincipal Jwt jwt) { return forward(orders,HttpMethod.GET,"/api/v1/admin/pedidos",null,jwt); }
    @PostMapping("/pedidos") ResponseEntity<byte[]> create(@RequestBody String body,@AuthenticationPrincipal Jwt jwt) { return forward(orders,HttpMethod.POST,"/api/v1/pedidos",body,jwt); }
    private ResponseEntity<byte[]> forward(RestClient client,HttpMethod method,String path,String body,Jwt jwt) {
        var request=client.method(method).uri(path).headers(headers -> headers.setBearerAuth(jwt.getTokenValue()));
        if (body!=null) request.contentType(MediaType.APPLICATION_JSON).body(body);
        return request.exchange((req,res) -> {
            var headers=new HttpHeaders();
            headers.setContentType(res.getHeaders().getContentType()==null?MediaType.APPLICATION_JSON:res.getHeaders().getContentType());
            if (res.getHeaders().getLocation()!=null) headers.setLocation(res.getHeaders().getLocation());
            return new ResponseEntity<>(res.getBody().readAllBytes(),headers,res.getStatusCode());
        });
    }
}
