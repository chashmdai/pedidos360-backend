package cl.duoc.pedidos360.bff;
import com.sun.net.httpserver.HttpServer;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.*;
@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT)
class BffContractTest {
    static final TestTokens TOKENS=new TestTokens();
    static final AtomicReference<String> BEARER=new AtomicReference<>();
    static final AtomicReference<String> BODY=new AtomicReference<>();
    static final HttpServer UPSTREAM=upstream();
    static HttpServer upstream() {
        try {
            var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
            server.createContext("/api/v1/",exchange -> {
                BEARER.set(exchange.getRequestHeaders().getFirst("Authorization"));
                BODY.set(new String(exchange.getRequestBody().readAllBytes(),StandardCharsets.UTF_8));
                boolean create=exchange.getRequestMethod().equals("POST");
                byte[] response=(create?"{\"id\":\"10000000-0000-0000-0000-000000000001\",\"estado\":\"REGISTERED\"}":"[]").getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set("Content-Type","application/json");
                if(create)exchange.getResponseHeaders().set("Location","/api/v1/pedidos/10000000-0000-0000-0000-000000000001");
                exchange.sendResponseHeaders(create?201:200,response.length);exchange.getResponseBody().write(response);exchange.close();
            });
            server.start();return server;
        } catch(Exception e){throw new IllegalStateException(e);}
    }
    @LocalServerPort int port;
    @DynamicPropertySource static void configure(DynamicPropertyRegistry r) {
        r.add("pedidos.security.tenant",()->"test-tenant"); r.add("pedidos.security.client",()->"test-spa");
        r.add("pedidos.security.issuer",TOKENS::issuer);r.add("pedidos.security.audience",()->TestTokens.AUDIENCE);r.add("pedidos.security.jwks",()->TOKENS.issuer()+"/jwks");
        r.add("pedidos.catalog-url",()->"http://127.0.0.1:"+UPSTREAM.getAddress().getPort());
        r.add("pedidos.orders-url",()->"http://127.0.0.1:"+UPSTREAM.getAddress().getPort());
    }
    @AfterAll static void cleanup(){UPSTREAM.stop(0);TOKENS.close();}
    @Test void preservesBearerBodyStatusAndLocation() throws Exception {
        String token=TOKENS.token("alice","Orders.Create Catalog.Read");
        String body="{\"items\":[{\"productoId\":\"10000000-0000-0000-0000-000000000001\",\"cantidad\":1}]}";
        var response=TestHttp.call(port,"POST","/api/v1/pedidos",body,token);
        assertEquals(201,response.statusCode());assertTrue(response.headers().firstValue("Location").orElseThrow().startsWith("/api/v1/pedidos/"));
        assertEquals(body,BODY.get());assertEquals("Bearer "+token,BEARER.get());
    }
    @Test void bffItselfRejectsInvalidAudienceAndMissingScopes() throws Exception {
        assertEquals(401,TestHttp.call(port,"GET","/api/v1/productos",null,null).statusCode());
        assertEquals(401,TestHttp.call(port,"GET","/api/v1/productos",null,TOKENS.token("alice","Catalog.Read","wrong",TOKENS.issuer(),600)).statusCode());
        assertEquals(403,TestHttp.call(port,"GET","/api/v1/productos",null,TOKENS.token("alice","Orders.Read")).statusCode());
        assertEquals(200,TestHttp.call(port,"GET","/api/v1/productos",null,TOKENS.token("alice","Catalog.Read")).statusCode());
    }
    @Test void identityOnlyReturnsVerifiedPublicClaimsAndIsNotCacheable() throws Exception {
        var token = TOKENS.token("alice", "Catalog.Read Orders.Read Orders.Create");
        var response = TestHttp.call(port, "GET", "/api/v1/me", null, token);
        assertEquals(200, response.statusCode());
        assertTrue(response.headers().firstValue("Cache-Control").orElseThrow().contains("no-store"));
        var json = new tools.jackson.databind.json.JsonMapper().readTree(response.body());
        assertEquals("alice", json.get("subjectId").asText());
        assertEquals("test-tenant", json.get("tenantId").asText());
        assertEquals("User", json.get("roles").get(0).asText());
        assertEquals(3, json.get("scopes").size());
        assertEquals(TestTokens.AUDIENCE, json.get("audience").get(0).asText());
        assertFalse(response.body().contains(token));
        assertFalse(json.has("accessToken"));
        assertEquals(403, TestHttp.call(port, "GET", "/api/v1/me", null, TOKENS.token("alice", "")).statusCode());
    }
    @Test void adminRequiresBothRoleAndScopeAndForwardsTheOriginalBearer() throws Exception {
        var path = "/api/v1/admin/pedidos";
        assertEquals(403, TestHttp.call(port, "GET", path, null, TOKENS.token("alice", "Orders.Read")).statusCode());
        var adminNoScope = TOKENS.withClaims("admin", "Catalog.Read", java.util.Map.of("roles", java.util.List.of("Admin")));
        assertEquals(403, TestHttp.call(port, "GET", path, null, adminNoScope).statusCode());
        var admin = TOKENS.withClaims("admin", "Orders.Read", java.util.Map.of("roles", java.util.List.of("Admin")));
        assertEquals(200, TestHttp.call(port, "GET", path, null, admin).statusCode());
        assertEquals("Bearer " + admin, BEARER.get());
    }
    @Test void rejectsWrongTenantClientVersionMissingExpiryFutureNbfAndWrongSignature() throws Exception {
        var invalid = new java.util.ArrayList<java.util.Map<String,Object>>();
        invalid.add(java.util.Map.of("tid", "another-tenant"));
        invalid.add(java.util.Map.of("azp", "another-client"));
        invalid.add(java.util.Map.of("ver", "1.0"));
        invalid.add(java.util.Collections.singletonMap("exp", null));
        invalid.add(java.util.Collections.singletonMap("aud", null));
        invalid.add(java.util.Collections.singletonMap("oid", null));
        invalid.add(java.util.Map.of("nbf", java.util.Date.from(java.time.Instant.now().plusSeconds(300))));
        invalid.add(java.util.Map.of("exp", java.util.Date.from(java.time.Instant.now().minusSeconds(300))));
        invalid.add(java.util.Map.of("iss", "https://wrong.invalid"));
        for (var claims : invalid) {
            assertEquals(401, TestHttp.call(port, "GET", "/api/v1/me", null,
                TOKENS.withClaims("alice", "Orders.Read", claims)).statusCode(), claims.keySet().toString());
        }
        try (var foreign = new TestTokens()) {
            var token = foreign.withClaims("alice", "Orders.Read", java.util.Map.of("iss", TOKENS.issuer()));
            assertEquals(401, TestHttp.call(port, "GET", "/api/v1/me", null, token).statusCode());
        }
    }
}
