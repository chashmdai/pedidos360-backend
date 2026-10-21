package cl.duoc.pedidos360.rabbitadmin.configuration;
import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.*;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;
@Configuration(proxyBeanMethods=false)
public class AdminConfiguration {
    @Bean RestClient brokerManagement(@Value("${pedidos.rabbit-admin.url}") String url,
            @Value("${pedidos.rabbit-admin.username}") String username,
            @Value("${pedidos.rabbit-admin.password}") String password) {
        var factory=new JdkClientHttpRequestFactory(HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2))
                .followRedirects(HttpClient.Redirect.NEVER).build());
        factory.setReadTimeout(Duration.ofSeconds(4));
        return RestClient.builder().baseUrl(url).requestFactory(factory)
                .defaultHeaders(headers -> headers.setBasicAuth(username,password)).build();
    }
}
