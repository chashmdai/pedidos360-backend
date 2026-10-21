package cl.duoc.pedidos360.insights.infrastructure;
import cl.duoc.pedidos360.insights.application.ProjectionStore;
import java.io.IOException;
import java.nio.file.Path;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.*;
import tools.jackson.databind.json.JsonMapper;
@Configuration(proxyBeanMethods=false)
public class ProjectionConfiguration {
    @Bean ProjectionStore auditStore(@Value("${pedidos.insights.directory}") String root,JsonMapper json) throws IOException {
        return new FileProjectionStore(Path.of(root,"audit"),json);
    }
    @Bean ProjectionStore salesStore(@Value("${pedidos.insights.directory}") String root,JsonMapper json) throws IOException {
        return new FileProjectionStore(Path.of(root,"sales"),json);
    }
}
