package cl.duoc.pedidos360.insights;
import cl.duoc.pedidos360.insights.application.ProjectionStore;
import cl.duoc.pedidos360.messaging.OrderRegisteredV1;
import java.math.BigDecimal;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
import org.springframework.beans.factory.annotation.*;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.*;
import tools.jackson.databind.json.JsonMapper;

/** HTTP read-model contract and authorization using a local signed fixture, without broker side effects. */
@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT)
class InsightsHttpContractTest {
    static final TestTokens TOKENS=new TestTokens();
    static final Path DIRECTORY=directory();
    static Path directory(){try{return Files.createTempDirectory("pedidos360-ep4-insights-http-");}catch(Exception e){throw new IllegalStateException(e);}}
    @LocalServerPort int port;
    @Autowired @Qualifier("auditStore") ProjectionStore audit;
    @Autowired @Qualifier("salesStore") ProjectionStore sales;
    @DynamicPropertySource static void configure(DynamicPropertyRegistry r) {
        r.add("pedidos.security.tenant",()->"test-tenant");r.add("pedidos.security.client",()->"test-spa");
        r.add("pedidos.security.issuer",TOKENS::issuer);r.add("pedidos.security.audience",()->TestTokens.AUDIENCE);r.add("pedidos.security.jwks",()->TOKENS.issuer()+"/jwks");
        r.add("pedidos.insights.directory",DIRECTORY::toString);r.add("spring.rabbitmq.dynamic",()->"false");
        r.add("spring.rabbitmq.listener.simple.auto-startup",()->"false");r.add("management.health.rabbit.enabled",()->"false");
        r.add("RABBIT_USER",()->"unused");r.add("RABBIT_PASSWORD",()->"unused-test-only");
    }
    @AfterAll static void close(){TOKENS.close();}
    String admin(){return TOKENS.withClaims("admin","Orders.Read",Map.of("roles",List.of("Admin")));}
    @Test void requiresJwtAdminAndScope() throws Exception {
        String path="/api/v1/admin/insights/sales";
        assertEquals(401,TestHttp.call(port,"GET",path,null,null).statusCode());
        assertEquals(403,TestHttp.call(port,"GET",path,null,TOKENS.token("user","Orders.Read")).statusCode());
        assertEquals(403,TestHttp.call(port,"GET",path,null,TOKENS.withClaims("admin","Catalog.Read",Map.of("roles",List.of("Admin")))).statusCode());
    }
    @Test void servesTenantScopedAuditAndDailyCurrencySummaryWithoutDoubleCounting() throws Exception {
        var event=new OrderRegisteredV1(1,UUID.randomUUID(),UUID.randomUUID(),"test-tenant",Instant.parse("2026-10-21T10:00:00Z"),new BigDecimal("30970.00"),"CLP",2);
        var foreign=new OrderRegisteredV1(1,UUID.randomUUID(),UUID.randomUUID(),"another-tenant",event.occurredAt(),new BigDecimal("999.00"),"USD",1);
        audit.saveOnce(event);audit.saveOnce(foreign);sales.saveOnce(event);sales.saveOnce(event);sales.saveOnce(foreign);
        var auditResponse=TestHttp.call(port,"GET","/api/v1/admin/insights/audit",null,admin());
        assertEquals(200,auditResponse.statusCode());assertTrue(auditResponse.body().contains(event.eventId().toString()));assertFalse(auditResponse.body().contains(foreign.eventId().toString()));
        var response=TestHttp.call(port,"GET","/api/v1/admin/insights/sales",null,admin());assertEquals(200,response.statusCode());
        var result=new JsonMapper().readTree(response.body());assertEquals(1,result.size());assertEquals(1,result.get(0).get("orders").asInt());
        assertEquals(0,new BigDecimal("30970.00").compareTo(result.get(0).get("total").decimalValue()));assertEquals("CLP",result.get(0).get("currency").asText());
    }
}
