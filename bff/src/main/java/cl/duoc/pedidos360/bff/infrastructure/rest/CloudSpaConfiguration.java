package cl.duoc.pedidos360.bff.infrastructure.rest;
import java.io.IOException;
import java.nio.file.Path;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.http.CacheControl;
import org.springframework.web.servlet.config.annotation.*;
import org.springframework.web.servlet.resource.PathResourceResolver;

/** Static hosting on the existing EC2, reached through HTTPS Gateway; no API authorization bypass. */
@Configuration(proxyBeanMethods=false)
@ConditionalOnProperty(name="pedidos.spa.enabled",havingValue="true")
public class CloudSpaConfiguration implements WebMvcConfigurer {
    private final String location;
    public CloudSpaConfiguration(@Value("${pedidos.spa.directory}") String directory) {
        location=Path.of(directory).toAbsolutePath().normalize().toUri().toString();
    }
    @Override public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/app/**").addResourceLocations(location)
            .setCacheControl(CacheControl.noStore()).resourceChain(true).addResolver(new PathResourceResolver() {
                @Override protected Resource getResource(String path,Resource root) throws IOException {
                    Resource resource=super.getResource(path,root);
                    if (resource!=null && resource.isReadable() && !path.isBlank()) return resource;
                    // Only known SPA routes fall back to HTML. Missing assets never return a misleading 200.
                    if (path.isEmpty() || path.matches("catalogo|pedidos|nuevo|sesion|administracion"))
                        return super.getResource("index.html",root);
                    return null;
                }
            });
    }
}
