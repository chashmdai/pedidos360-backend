package cl.duoc.pedidos360.orders;

import static org.junit.jupiter.api.Assertions.*;

import cl.duoc.pedidos360.orders.application.OrderRepository;
import java.time.Duration;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.*;

/** Without reachable brokers the order still commits and its stream event stays pending (KAFKA_UNCONFIRMED). */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = {
        "pedidos.kafka.enabled=true", "pedidos.kafka.relay.initial-delay-ms=200", "pedidos.kafka.relay.confirm-timeout-ms=2000",
        "spring.kafka.bootstrap-servers=127.0.0.1:1",
        // Test-only: bound the metadata wait so the deferral is observed quickly.
        "spring.kafka.producer.properties.max.block.ms=1000",
        "spring.kafka.admin.fail-fast=false", "spring.kafka.admin.operation-timeout=1s"})
@ExtendWith(OutputCaptureExtension.class)
@org.springframework.test.annotation.DirtiesContext
class OrderStreamOutboxUnavailableTest {
    static final TestDatabase DB = new TestDatabase();
    static final TestTokens TOKENS = new TestTokens();
    @Autowired OrderRepository orders;
    @Autowired JdbcTemplate jdbc;

    @DynamicPropertySource static void configure(DynamicPropertyRegistry r) {
        DB.properties(r);
        r.add("pedidos.security.issuer", TOKENS::issuer); r.add("pedidos.security.jwks", () -> TOKENS.issuer() + "/jwks");
        r.add("pedidos.security.audience", () -> TestTokens.AUDIENCE);
        r.add("pedidos.security.tenant", () -> "test-tenant"); r.add("pedidos.security.client", () -> "test-spa");
        r.add("pedidos.catalog-url", () -> "http://127.0.0.1:1");
    }

    @AfterAll static void close(@Autowired org.springframework.context.ConfigurableApplicationContext context) {
        context.stop(); // stop the relay scheduler and Kafka producers before their containers disappear
        DB.close(); TOKENS.close(); }

    @Test void eventIsDeferredAndRetriedWhileKafkaIsUnavailable(CapturedOutput output) throws Exception {
        var saved = orders.save(OrderStreamOutboxIntegrationTest.order());
        String id = saved.id().toString();
        assertEquals(1, jdbc.queryForObject("SELECT COUNT(*) FROM purchase_orders WHERE id=?", Integer.class, id), "the order commits");
        long deadline = System.nanoTime() + Duration.ofSeconds(30).toNanos();
        while (jdbc.queryForObject("SELECT attempts FROM order_stream_outbox WHERE order_id=?", Integer.class, id) == 0) {
            assertTrue(System.nanoTime() < deadline, "relay never attempted");
            Thread.sleep(200);
        }
        var row = jdbc.queryForMap("SELECT event_id,published_at,last_error_code,"
                + "TIMESTAMPDIFF(MICROSECOND,CURRENT_TIMESTAMP(6),next_attempt_at) AS wait_us FROM order_stream_outbox WHERE order_id=?", id);
        assertNull(row.get("published_at"), "never marked published without acks=all");
        assertEquals("KAFKA_UNCONFIRMED", row.get("last_error_code"));
        assertTrue(((Number) row.get("wait_us")).longValue() > 0, "next attempt is scheduled in the future (5 s backoff)");
        assertTrue(output.getOut().contains("PUBLISH_DEFERRED eventId=" + row.get("event_id") + " orderId=" + id), output.getOut());
    }
}
