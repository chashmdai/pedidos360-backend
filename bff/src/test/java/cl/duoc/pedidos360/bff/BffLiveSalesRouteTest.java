package cl.duoc.pedidos360.bff;

import static org.junit.jupiter.api.Assertions.*;

import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/** EP5 route GET /api/v1/ventas/en-vivo -> sales-stream-service with the original bearer. */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BffLiveSalesRouteTest {
    static final TestTokens TOKENS = new TestTokens();
    static final AtomicReference<String> PATH = new AtomicReference<>();
    static final AtomicReference<String> BEARER = new AtomicReference<>();
    static final String BODY = "{\"fecha\":\"2026-11-24\",\"productos\":[],\"alertas\":[]}";
    static final HttpServer SALES = sales();

    static HttpServer sales() {
        try {
            var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/", exchange -> {
                PATH.set(exchange.getRequestURI().getPath());
                BEARER.set(exchange.getRequestHeaders().getFirst("Authorization"));
                byte[] body = BODY.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set("Content-Type", "application/json");
                exchange.sendResponseHeaders(200, body.length); exchange.getResponseBody().write(body); exchange.close();
            });
            server.start(); return server;
        } catch (Exception e) { throw new IllegalStateException(e); }
    }

    @LocalServerPort int port;

    @DynamicPropertySource static void configure(DynamicPropertyRegistry r) {
        r.add("pedidos.security.tenant", () -> "test-tenant"); r.add("pedidos.security.client", () -> "test-spa");
        r.add("pedidos.security.issuer", TOKENS::issuer); r.add("pedidos.security.audience", () -> TestTokens.AUDIENCE);
        r.add("pedidos.security.jwks", () -> TOKENS.issuer() + "/jwks");
        r.add("pedidos.sales-stream-url", () -> "http://127.0.0.1:" + SALES.getAddress().getPort());
    }

    @AfterAll static void cleanup() { SALES.stop(0); TOKENS.close(); }

    @Test void requiresOrdersReadAndForwardsBearerToSalesStream() throws Exception {
        String path = "/api/v1/ventas/en-vivo";
        assertEquals(401, TestHttp.call(port, "GET", path, null, null).statusCode());
        assertEquals(403, TestHttp.call(port, "GET", path, null, TOKENS.token("alice", "Catalog.Read Orders.Create")).statusCode());
        assertNull(PATH.get(), "rejected requests never reach sales-stream-service");
        String token = TOKENS.token("alice", "Orders.Read");
        var response = TestHttp.call(port, "GET", path, null, token);
        assertEquals(200, response.statusCode());
        assertEquals(BODY, response.body());
        assertTrue(response.headers().firstValue("Cache-Control").orElseThrow().contains("no-store"));
        assertEquals(path, PATH.get());
        assertEquals("Bearer " + token, BEARER.get());
    }
}
