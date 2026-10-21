package cl.duoc.pedidos360.orders;
import cl.duoc.pedidos360.orders.application.OrderRepository;
import cl.duoc.pedidos360.orders.domain.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.AfterAll;
import static org.junit.jupiter.api.Assertions.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.*;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties={"pedidos.messaging.enabled=true","pedidos.messaging.initial-delay-ms=3600000",
        "RABBIT_USER=unused-test-user","RABBIT_PASSWORD=unused-test-password","management.health.rabbit.enabled=false"})
class OrderOutboxIntegrationTest {
    static final TestDatabase DB=new TestDatabase();
    static final TestTokens TOKENS=new TestTokens();
    @Autowired OrderRepository orders;
    @Autowired JdbcTemplate jdbc;
    @Autowired PlatformTransactionManager transactions;
    @DynamicPropertySource static void configure(DynamicPropertyRegistry r) {
        DB.properties(r);r.add("pedidos.security.issuer",TOKENS::issuer);
        r.add("pedidos.security.jwks",()->TOKENS.issuer()+"/jwks");
        r.add("pedidos.security.audience",()->TestTokens.AUDIENCE);
        r.add("pedidos.security.tenant",()->"test-tenant");r.add("pedidos.security.client",()->"test-spa");
        r.add("pedidos.catalog-url",()->"http://127.0.0.1:1");
    }
    Order order() { return new Order(UUID.randomUUID(),new OwnerId("test-tenant","alice"),
        List.of(new OrderItem(UUID.randomUUID(),"Producto",new Money(new BigDecimal("125.00"),"CLP"),2)),Instant.now(),Order.Status.REGISTERED); }
    @AfterAll static void close() { DB.close();TOKENS.close(); }
    @Test void orderAndEventCommitTogetherWithoutContactingBroker() {
        var saved=orders.save(order());
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM order_event_outbox WHERE order_id=? AND published_at IS NULL",Integer.class,saved.id().toString()));
        var payload=jdbc.queryForObject("SELECT payload FROM order_event_outbox WHERE order_id=?",String.class,saved.id().toString());
        assertTrue(payload.contains(saved.id().toString()));
        assertFalse(payload.contains("alice"),"Event should not transmit the user's identity");
    }
    @Test void rollbackCannotLeaveOrphanOrderOrEvent() {
        var candidate=order();
        new TransactionTemplate(transactions).executeWithoutResult(status -> { orders.save(candidate);status.setRollbackOnly(); });
        assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM purchase_orders WHERE id=?",Integer.class,candidate.id().toString()));
        assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM order_event_outbox WHERE order_id=?",Integer.class,candidate.id().toString()));
    }
}
