package cl.duoc.pedidos360.kafkaadmin;

import static org.junit.jupiter.api.Assertions.*;

import cl.duoc.pedidos360.kafkaadmin.api.KafkaAdminController;
import java.io.FileReader;
import java.lang.reflect.Method;
import java.nio.file.Path;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.web.bind.annotation.RequestMapping;
import org.yaml.snakeyaml.Yaml;

/** contracts/kafka-admin-openapi.yaml, report table 14 and the controller expose exactly the same operations. */
class OpenApiContractTest {
    static final Set<String> TABLE_14 = Set.of("GET /cluster", "GET /topics", "GET /topics/{name}", "POST /topics",
            "PATCH /topics/{name}/configs", "POST /topics/{name}/partitions", "DELETE /topics/{name}",
            "GET /consumer-groups", "GET /consumer-groups/{groupId}");

    @Test @SuppressWarnings("unchecked")
    void contractControllerAndReportAgree() throws Exception {
        Map<String, Object> spec;
        try (var reader = new FileReader(Path.of("..", "contracts", "kafka-admin-openapi.yaml").toFile())) { spec = new Yaml().load(reader); }
        var documented = new TreeSet<String>();
        ((Map<String, Map<String, Object>>) spec.get("paths")).forEach((path, operations) -> operations.keySet().stream()
                .filter(m -> !m.equals("parameters")).forEach(m -> documented.add(m.toUpperCase() + " " + path)));
        assertEquals(new TreeSet<>(TABLE_14), documented);
        assertTrue(((List<Map<String, Object>>) spec.get("servers")).getFirst().get("url").toString().endsWith("/api/v1/admin/kafka"));

        var base = AnnotatedElementUtils.findMergedAnnotation(KafkaAdminController.class, RequestMapping.class).path()[0];
        assertEquals("/api/v1/admin/kafka", base);
        var implemented = new TreeSet<String>();
        for (Method method : KafkaAdminController.class.getDeclaredMethods()) {
            var mapping = AnnotatedElementUtils.findMergedAnnotation(method, RequestMapping.class);
            if (mapping != null) implemented.add(mapping.method()[0].name() + " " + mapping.path()[0]);
        }
        assertEquals(new TreeSet<>(TABLE_14), implemented);
    }
}
