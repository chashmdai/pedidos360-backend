package cl.duoc.pedidos360.orders;
import com.sun.net.httpserver.HttpServer;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.*;
import tools.jackson.databind.json.JsonMapper;
@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrdersIntegrationTest {
    static final TestDatabase DB=new TestDatabase();
    static final TestTokens TOKENS=new TestTokens();
    static final AtomicReference<String> PRICE=new AtomicReference<>("8990.00");
    static final AtomicReference<String> BEARER=new AtomicReference<>();
    static final HttpServer CATALOG=catalog();
    static HttpServer catalog() {
        try {
            var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
            server.createContext("/api/v1/productos/",exchange -> {
                BEARER.set(exchange.getRequestHeaders().getFirst("Authorization"));
                String id=exchange.getRequestURI().getPath().substring("/api/v1/productos/".length());
                byte[] body=("{\"id\":\""+id+"\",\"nombre\":\"Café\",\"precio\":"+PRICE.get()+",\"moneda\":\"CLP\",\"disponible\":true}").getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set("Content-Type","application/json");
                exchange.sendResponseHeaders(200,body.length);exchange.getResponseBody().write(body);exchange.close();
            });
            server.start();return server;
        } catch(Exception e) { throw new IllegalStateException(e); }
    }
    @LocalServerPort int port;
    @Autowired JdbcTemplate jdbc;
    @DynamicPropertySource static void configure(DynamicPropertyRegistry r) {
        r.add("pedidos.security.tenant",()->"test-tenant"); r.add("pedidos.security.client",()->"test-spa");
        DB.properties(r); r.add("pedidos.security.issuer",TOKENS::issuer); r.add("pedidos.security.audience",()->TestTokens.AUDIENCE);
        r.add("pedidos.security.jwks",()->TOKENS.issuer()+"/jwks");
        r.add("pedidos.catalog-url",()->"http://127.0.0.1:"+CATALOG.getAddress().getPort());
    }
    @AfterAll static void cleanup() { CATALOG.stop(0); DB.close(); TOKENS.close(); }
    @Test void createsMultitemOrderPersistsSnapshotsAndIsolatesOwner() throws Exception {
        PRICE.set("8990.00");
        String token=TOKENS.token("alice","Orders.Create Orders.Read Catalog.Read");
        String body="{\"items\":[{\"productoId\":\"10000000-0000-0000-0000-000000000001\",\"cantidad\":2},{\"productoId\":\"10000000-0000-0000-0000-000000000002\",\"cantidad\":1}]}";
        var created=TestHttp.call(port,"POST","/api/v1/pedidos",body,token);
        assertEquals(201,created.statusCode(),created.body());
        var json=new JsonMapper().readTree(created.body());String id=json.get("id").asText();
        assertEquals(26970,json.get("total").asInt());assertEquals(2,json.get("items").size()); assertEquals("REGISTERED",json.get("estado").asText());
        assertEquals("Bearer "+token,BEARER.get());
        PRICE.set("10000.00");
        var stored=TestHttp.call(port,"GET","/api/v1/pedidos/"+id,null,token);
        assertEquals(json,new JsonMapper().readTree(stored.body()),"Persisted response must preserve the creation contract, including time precision");
        assertEquals(26970,new JsonMapper().readTree(stored.body()).get("total").asInt());
        assertEquals(404,TestHttp.call(port,"GET","/api/v1/pedidos/"+id,null,TOKENS.token("bob","Orders.Read")).statusCode());
        assertEquals("[]",TestHttp.call(port,"GET","/api/v1/pedidos",null,TOKENS.token("bob","Orders.Read")).body());
        assertEquals(2,jdbc.queryForObject("SELECT COUNT(*) FROM order_items WHERE order_id=?",Integer.class,id));
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM flyway_schema_history WHERE success=1",Integer.class));
    }
    @Test void missingScopeAndInvalidRequestCannotCreateOrder() throws Exception {
        assertEquals(403,TestHttp.call(port,"POST","/api/v1/pedidos","{\"items\":[]}",TOKENS.token("reader","Orders.Create")).statusCode());
        assertEquals(400,TestHttp.call(port,"POST","/api/v1/pedidos","{\"items\":[null]}",TOKENS.token("alice","Orders.Create Catalog.Read")).statusCode());
    }
    @Test void administrativeQueryRequiresRoleAndScopeAndDoesNotWidenOwnOrders() throws Exception {
        var user = TOKENS.token("role-test-user", "Orders.Create Orders.Read Catalog.Read");
        var body = "{\"items\":[{\"productoId\":\"10000000-0000-0000-0000-000000000001\",\"cantidad\":1}]}";
        var created = TestHttp.call(port, "POST", "/api/v1/pedidos", body, user);
        assertEquals(201, created.statusCode());
        var id = new JsonMapper().readTree(created.body()).get("id").asText();
        var admin = TOKENS.withClaims("role-test-admin", "Orders.Read", java.util.Map.of("roles", java.util.List.of("Admin")));
        assertEquals(403, TestHttp.call(port, "GET", "/api/v1/admin/pedidos", null, user).statusCode());
        assertEquals(403, TestHttp.call(port, "GET", "/api/v1/admin/pedidos", null,
            TOKENS.withClaims("role-test-admin", "Catalog.Read", java.util.Map.of("roles", java.util.List.of("Admin")))).statusCode());
        var all = TestHttp.call(port, "GET", "/api/v1/admin/pedidos", null, admin);
        assertEquals(200, all.statusCode()); assertTrue(all.body().contains(id));
        assertEquals("[]", TestHttp.call(port, "GET", "/api/v1/pedidos", null, admin).body());
        assertEquals(404, TestHttp.call(port, "GET", "/api/v1/pedidos/" + id, null, admin).statusCode());
        jdbc.update("UPDATE purchase_orders SET owner_tenant=? WHERE id=?", "external-tenant", id);
        assertFalse(TestHttp.call(port, "GET", "/api/v1/admin/pedidos", null, admin).body().contains(id));
    }
}
