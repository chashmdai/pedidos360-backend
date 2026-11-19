package cl.duoc.pedidos360.kafkaadmin;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.*;
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.junit.jupiter.api.*;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** Report table 14 and evidence E-14 against a real broker: codes 201/200/204/400/401/403/404/409. */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@DirtiesContext
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class KafkaAdminIntegrationTest {
    static final TestKafka KAFKA = new TestKafka();
    static final TestTokens TOKENS = new TestTokens();
    static final JsonMapper JSON = new JsonMapper();
    static final String BASE = "/api/v1/admin/kafka";
    static final String LAB = "pedidos360.lab.demo";
    static final String BUSINESS = "pedidos360.orders.registered.v1";

    @DynamicPropertySource static void configure(DynamicPropertyRegistry r) {
        r.add("spring.kafka.bootstrap-servers", KAFKA::bootstrap);
        r.add("pedidos.security.issuer", TOKENS::issuer); r.add("pedidos.security.jwks", () -> TOKENS.issuer() + "/jwks");
        r.add("pedidos.security.audience", () -> TestTokens.AUDIENCE);
        r.add("pedidos.security.tenant", () -> "test-tenant"); r.add("pedidos.security.client", () -> "test-spa");
    }

    @BeforeAll static void businessTopicExists() throws Exception {
        try (var admin = Admin.create(Map.of("bootstrap.servers", KAFKA.bootstrap()))) {
            admin.createTopics(List.of(new NewTopic(BUSINESS, 3, (short) 1))).all().get();
        }
    }

    @AfterAll static void close(@org.springframework.beans.factory.annotation.Autowired org.springframework.context.ConfigurableApplicationContext context) {
        context.stop(); KAFKA.close(); TOKENS.close();
    }

    @LocalServerPort int port;

    String admin() { return TOKENS.withClaims("admin", "Orders.Read", Map.of("roles", List.of("Admin"))); }

    java.net.http.HttpResponse<String> call(String method, String path, String body, String token) throws Exception {
        return TestHttp.call(port, method, BASE + path, body, token);
    }

    JsonNode ok(int expected, java.net.http.HttpResponse<String> response) {
        assertEquals(expected, response.statusCode(), response.body());
        return response.body().isBlank() ? null : JSON.readTree(response.body());
    }

    @Test @Order(1)
    void authorizationRequiresAdminRoleAndOrdersRead() throws Exception {
        for (var path : List.of("/cluster", "/topics", "/topics/" + BUSINESS, "/consumer-groups")) {
            assertEquals(401, call("GET", path, null, null).statusCode(), path);
            assertEquals(403, call("GET", path, null, TOKENS.token("alice", "Orders.Read")).statusCode(), "User role: " + path);
            assertEquals(403, call("GET", path, null, TOKENS.withClaims("admin", "Catalog.Read", Map.of("roles", List.of("Admin")))).statusCode(),
                    "Admin without Orders.Read: " + path);
        }
        String create = "{\"name\":\"pedidos360.lab.user\",\"partitions\":1,\"replicationFactor\":1}";
        assertEquals(403, call("POST", "/topics", create, TOKENS.token("alice", "Orders.Read")).statusCode());
        assertEquals(403, call("DELETE", "/topics/" + BUSINESS, null, TOKENS.token("alice", "Orders.Read")).statusCode());
    }

    @Test @Order(2)
    void clusterAndTopicListing() throws Exception {
        var cluster = ok(200, call("GET", "/cluster", null, admin()));
        assertFalse(cluster.get("clusterId").asString().isBlank());
        assertEquals(1, cluster.get("brokers").size());
        assertNotNull(cluster.get("controller").get("id"));
        var topics = ok(200, call("GET", "/topics", null, admin()));
        var names = new ArrayList<String>(); topics.forEach(t -> names.add(t.get("name").asString()));
        assertTrue(names.contains(BUSINESS));
        assertTrue(names.stream().noneMatch(n -> n.startsWith("__")), "internal topics hidden by default");
    }

    @Test @Order(3)
    void e14TopicLifecycle() throws Exception {
        // POST /topics -> 201
        var created = ok(201, call("POST", "/topics", "{\"name\":\"" + LAB + "\",\"partitions\":3,\"replicationFactor\":1,"
                + "\"configs\":{\"retention.ms\":\"3600000\",\"cleanup.policy\":\"delete\"}}", admin()));
        assertEquals(3, created.get("partitions").size());
        assertEquals("3600000", created.get("configs").get("retention.ms").get("value").asString());
        assertEquals("DYNAMIC_TOPIC_CONFIG", created.get("configs").get("retention.ms").get("source").asString());
        assertEquals(409, call("POST", "/topics", "{\"name\":\"" + LAB + "\",\"partitions\":3,\"replicationFactor\":1}", admin()).statusCode(), "already exists");

        // GET /topics/{name} -> 200 with leader, replicas and ISR per partition
        var detail = ok(200, call("GET", "/topics/" + LAB, null, admin()));
        detail.get("partitions").forEach(p -> { assertNotNull(p.get("leader")); assertEquals(1, p.get("isr").size()); });
        assertFalse(detail.get("protectedTopic").asBoolean());

        // PATCH /topics/{name}/configs (retention.ms) -> 200
        var patched = ok(200, call("PATCH", "/topics/" + LAB + "/configs", "{\"configs\":{\"retention.ms\":\"7200000\"}}", admin()));
        assertEquals("7200000", patched.get("configs").get("retention.ms").get("value").asString());
        assertEquals(400, call("PATCH", "/topics/" + LAB + "/configs", "{\"configs\":{\"compression.type\":\"gzip\"}}", admin()).statusCode(), "not whitelisted");
        assertEquals(400, call("PATCH", "/topics/" + LAB + "/configs", "{\"configs\":{\"min.insync.replicas\":\"2\"}}", admin()).statusCode(), "above RF");
        assertEquals(400, call("PATCH", "/topics/" + LAB + "/configs", "{\"configs\":{}}", admin()).statusCode(), "empty body");

        // POST /topics/{name}/partitions -> 200, only increases
        var grown = ok(200, call("POST", "/topics/" + LAB + "/partitions", "{\"partitions\":5}", admin()));
        assertEquals(5, grown.get("partitions").size());
        assertEquals(400, call("POST", "/topics/" + LAB + "/partitions", "{\"partitions\":4}", admin()).statusCode(), "no decrease");
        assertEquals(400, call("POST", "/topics/" + LAB + "/partitions", "{\"partitions\":13}", admin()).statusCode(), "max 12");

        // DELETE /topics/{name} -> 204, then 404
        assertEquals(204, call("DELETE", "/topics/" + LAB, null, admin()).statusCode());
        long deadline = System.nanoTime() + Duration.ofSeconds(15).toNanos();
        int status;
        do { status = call("GET", "/topics/" + LAB, null, admin()).statusCode(); } while (status != 404 && System.nanoTime() < deadline);
        assertEquals(404, status);
        assertEquals(404, call("DELETE", "/topics/" + LAB, null, admin()).statusCode());
    }

    @Test @Order(4)
    void businessAndForeignTopicsAreProtected() throws Exception {
        assertEquals(409, call("DELETE", "/topics/" + BUSINESS, null, admin()).statusCode(), "business topic");
        assertEquals(409, call("POST", "/topics/" + BUSINESS + "/partitions", "{\"partitions\":6}", admin()).statusCode());
        assertEquals(409, call("DELETE", "/topics/__consumer_offsets", null, admin()).statusCode(), "internal topic");
        assertEquals(409, call("DELETE", "/topics/someone.else", null, admin()).statusCode(), "outside the laboratory prefix");
        assertEquals(400, call("POST", "/topics", "{\"name\":\"" + BUSINESS + "\",\"partitions\":3,\"replicationFactor\":1}", admin()).statusCode());
        assertEquals(400, call("POST", "/topics", "{\"name\":\"other.topic\",\"partitions\":3,\"replicationFactor\":1}", admin()).statusCode());
        assertEquals(400, call("POST", "/topics", "{\"name\":\"pedidos360.lab.bad\",\"partitions\":13,\"replicationFactor\":1}", admin()).statusCode(), "partitions 1-12");
        assertEquals(400, call("POST", "/topics", "{\"name\":\"pedidos360.lab.bad\",\"partitions\":1,\"replicationFactor\":4}", admin()).statusCode(), "replicas 1-3");
        assertEquals(400, call("POST", "/topics", "{\"name\":\"pedidos360.lab.bad\",\"partitions\":1,\"replicationFactor\":3}", admin()).statusCode(),
                "more replicas than brokers");
        assertEquals(400, call("POST", "/topics", "{\"name\":\"pedidos360.lab.bad name\",\"partitions\":1,\"replicationFactor\":1}", admin()).statusCode());
        assertEquals(404, call("GET", "/topics/pedidos360.lab.missing", null, admin()).statusCode());
        var problem = JSON.readTree(call("DELETE", "/topics/" + BUSINESS, null, admin()).body());
        assertEquals(409, problem.get("status").asInt(), "ProblemDetails body");
        assertTrue(call("DELETE", "/topics/" + BUSINESS, null, admin()).headers().firstValue("Content-Type").orElseThrow().contains("problem+json"));
    }

    @Test @Order(5)
    void consumerGroupOffsetsAndLag() throws Exception {
        String topic = "pedidos360.lab.lag";
        ok(201, call("POST", "/topics", "{\"name\":\"" + topic + "\",\"partitions\":1,\"replicationFactor\":1}", admin()));
        try (var producer = new KafkaProducer<>(Map.<String, Object>of("bootstrap.servers", KAFKA.bootstrap()), new StringSerializer(), new StringSerializer())) {
            for (int i = 0; i < 3; i++) producer.send(new ProducerRecord<>(topic, "k" + i, "v" + i)).get();
        }
        try (var consumer = new KafkaConsumer<>(Map.<String, Object>of("bootstrap.servers", KAFKA.bootstrap(), "group.id", "pedidos360-lab-group"),
                new StringDeserializer(), new StringDeserializer())) {
            consumer.commitSync(Map.of(new TopicPartition(topic, 0), new OffsetAndMetadata(1)));   // one of three processed
        }
        var groups = ok(200, call("GET", "/consumer-groups", null, admin()));
        var ids = new ArrayList<String>(); groups.forEach(g -> ids.add(g.get("groupId").asString()));
        assertTrue(ids.contains("pedidos360-lab-group"), groups.toString());
        var group = ok(200, call("GET", "/consumer-groups/pedidos360-lab-group", null, admin()));
        var partition = group.get("partitions").get(0);
        assertEquals(topic, partition.get("topic").asString());
        assertEquals(1, partition.get("committedOffset").asLong());
        assertEquals(3, partition.get("logEndOffset").asLong());
        assertEquals(2, partition.get("lag").asLong());
        assertEquals(2, group.get("totalLag").asLong());
        assertEquals("EMPTY", group.get("state").asString());
        assertEquals(404, call("GET", "/consumer-groups/pedidos360-no-such-group", null, admin()).statusCode());
        assertEquals(204, call("DELETE", "/topics/" + topic, null, admin()).statusCode());
    }
}
