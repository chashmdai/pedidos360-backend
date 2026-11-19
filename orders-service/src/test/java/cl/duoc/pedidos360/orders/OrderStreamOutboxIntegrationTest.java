package cl.duoc.pedidos360.orders;

import static org.junit.jupiter.api.Assertions.*;

import cl.duoc.pedidos360.kafka.OrderRegisteredStreamV1;
import cl.duoc.pedidos360.orders.application.OrderRepository;
import cl.duoc.pedidos360.orders.domain.*;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.*;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import tools.jackson.databind.json.JsonMapper;

/** Streaming outbox + relay against real MySQL and Kafka. The RabbitMQ outbox stays enabled alongside. */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = {
        "pedidos.kafka.enabled=true", "pedidos.kafka.relay.initial-delay-ms=500",
        "pedidos.messaging.enabled=true", "pedidos.messaging.initial-delay-ms=3600000",
        "RABBIT_USER=unused-test-user", "RABBIT_PASSWORD=unused-test-password", "management.health.rabbit.enabled=false"})
@ExtendWith(OutputCaptureExtension.class)
@org.springframework.test.annotation.DirtiesContext
class OrderStreamOutboxIntegrationTest {
    static final TestDatabase DB = new TestDatabase();
    static final TestKafka KAFKA = new TestKafka();
    static final TestTokens TOKENS = new TestTokens();
    static final String TOPIC = "pedidos360.orders.registered.v1";
    @Autowired OrderRepository orders;
    @Autowired JdbcTemplate jdbc;
    @Autowired PlatformTransactionManager transactions;

    @DynamicPropertySource static void configure(DynamicPropertyRegistry r) {
        DB.properties(r); KAFKA.properties(r);
        r.add("pedidos.security.issuer", TOKENS::issuer); r.add("pedidos.security.jwks", () -> TOKENS.issuer() + "/jwks");
        r.add("pedidos.security.audience", () -> TestTokens.AUDIENCE);
        r.add("pedidos.security.tenant", () -> "test-tenant"); r.add("pedidos.security.client", () -> "test-spa");
        r.add("pedidos.catalog-url", () -> "http://127.0.0.1:1");
    }

    @AfterAll static void close(@Autowired org.springframework.context.ConfigurableApplicationContext context) {
        context.stop(); // stop the relay scheduler and Kafka producers before their containers disappear
        KAFKA.close(); DB.close(); TOKENS.close(); }

    static Order order() {
        return new Order(UUID.randomUUID(), new OwnerId("test-tenant", "alice"), List.of(
                new OrderItem(UUID.randomUUID(), "Café de especialidad", new Money(new BigDecimal("18990.00"), "CLP"), 1),
                new OrderItem(UUID.randomUUID(), "Taza de cerámica", new Money(new BigDecimal("5990.00"), "CLP"), 2)),
                Instant.now(), Order.Status.REGISTERED);
    }

    int count(String sql, Object... args) { return jdbc.queryForObject(sql, Integer.class, args); }

    @Test void bothOutboxesCommitWithTheOrderAndRelayPublishesWithKeyOrderId(CapturedOutput output) throws Exception {
        var saved = orders.save(order());
        String id = saved.id().toString();
        assertEquals(1, count("SELECT COUNT(*) FROM order_event_outbox WHERE order_id=?", id), "RabbitMQ outbox unchanged");
        assertEquals(1, count("SELECT COUNT(*) FROM order_stream_outbox WHERE order_id=?", id));

        long deadline = System.nanoTime() + Duration.ofSeconds(30).toNanos();
        while (count("SELECT COUNT(*) FROM order_stream_outbox WHERE order_id=? AND published_at IS NOT NULL", id) == 0) {
            assertTrue(System.nanoTime() < deadline, "relay did not confirm the event");
            Thread.sleep(200);
        }
        var row = jdbc.queryForMap("SELECT event_id,attempts,last_error_code FROM order_stream_outbox WHERE order_id=?", id);
        assertEquals(1, ((Number) row.get("attempts")).intValue());
        assertNull(row.get("last_error_code"));
        String eventId = row.get("event_id").toString();

        var record = KAFKA.read(TOPIC, 1, Duration.ofSeconds(20)).stream().filter(r -> id.equals(r.key())).findFirst().orElseThrow();
        assertFalse(record.headers().iterator().hasNext(), "no Java type headers");
        assertFalse(record.value().contains("alice"), "the event must not carry the user's identity");
        var event = new JsonMapper().readValue(record.value(), OrderRegisteredStreamV1.class);
        assertEquals(UUID.fromString(eventId), event.eventId());
        assertEquals(saved.id(), event.orderId());
        assertEquals("test-tenant", event.tenantId());
        assertEquals("CLP", event.currency());
        assertEquals(0, new BigDecimal("30970.00").compareTo(event.total()));
        assertEquals(2, event.itemCount());
        assertEquals(0, new BigDecimal("11980.00").compareTo(event.items().get(1).lineTotal()));
        assertTrue(output.getOut().contains("PUBLISH_CONFIRMED eventId=" + eventId + " orderId=" + id + " topic=" + TOPIC
                + " partition=" + record.partition() + " offset=" + record.offset()), "confirmation log with topic, partition and offset");
    }

    @Test void rollbackLeavesNoOrderNorEventInEitherOutbox() {
        var candidate = order();
        new TransactionTemplate(transactions).executeWithoutResult(status -> { orders.save(candidate); status.setRollbackOnly(); });
        String id = candidate.id().toString();
        assertEquals(0, count("SELECT COUNT(*) FROM purchase_orders WHERE id=?", id));
        assertEquals(0, count("SELECT COUNT(*) FROM order_event_outbox WHERE order_id=?", id));
        assertEquals(0, count("SELECT COUNT(*) FROM order_stream_outbox WHERE order_id=?", id));
    }
}
