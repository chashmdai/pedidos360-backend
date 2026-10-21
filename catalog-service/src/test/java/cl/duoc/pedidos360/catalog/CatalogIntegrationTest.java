package cl.duoc.pedidos360.catalog;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.*;
import tools.jackson.databind.json.JsonMapper;
@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT)
class CatalogIntegrationTest {
    static final TestDatabase DB=new TestDatabase();
    static final TestTokens TOKENS=new TestTokens();
    @LocalServerPort int port;
    @Autowired JdbcTemplate jdbc;
    @DynamicPropertySource static void configure(DynamicPropertyRegistry r) {
        r.add("pedidos.security.tenant",()->"test-tenant"); r.add("pedidos.security.client",()->"test-spa");
        DB.properties(r);
        r.add("spring.flyway.locations",()->"classpath:db/migration,classpath:db/local");
        r.add("pedidos.security.issuer",TOKENS::issuer); r.add("pedidos.security.audience",()->TestTokens.AUDIENCE);
        r.add("pedidos.security.jwks",()->TOKENS.issuer()+"/jwks");
    }
    @AfterAll static void cleanup() { DB.close(); TOKENS.close(); }
    @Test void flywayAndProductHttpContract() throws Exception {
        var response=TestHttp.call(port,"GET","/api/v1/productos",null,TOKENS.token("alice","Catalog.Read"));
        assertEquals(200,response.statusCode());
        var products=new JsonMapper().readTree(response.body());
        assertEquals(2,products.size());
        assertEquals("CLP",products.get(0).get("moneda").asText());
        assertTrue(products.get(0).has("id")); assertTrue(products.get(0).has("precio")); assertFalse(products.get(0).has("active"));
        assertEquals(2,jdbc.queryForObject("SELECT COUNT(*) FROM flyway_schema_history WHERE success=1",Integer.class));
    }
    @Test void signatureIssuerAudienceExpiryAndScopeAreEnforced() throws Exception {
        String path="/api/v1/productos";
        assertEquals(401,TestHttp.call(port,"GET",path,null,null).statusCode());
        assertEquals(401,TestHttp.call(port,"GET",path,null,"invalid.jwt.value").statusCode());
        String signed=TOKENS.token("alice","Catalog.Read");
        int signature=signed.lastIndexOf('.')+1;
        String tampered=signed.substring(0,signature)+(signed.charAt(signature)=='A'?'B':'A')+signed.substring(signature+1);
        assertEquals(401,TestHttp.call(port,"GET",path,null,tampered).statusCode());
        assertEquals(401,TestHttp.call(port,"GET",path,null,TOKENS.token("alice","Catalog.Read","wrong",TOKENS.issuer(),600)).statusCode());
        assertEquals(401,TestHttp.call(port,"GET",path,null,TOKENS.token("alice","Catalog.Read",TestTokens.AUDIENCE,"https://wrong.invalid",600)).statusCode());
        assertEquals(401,TestHttp.call(port,"GET",path,null,TOKENS.token("alice","Catalog.Read",TestTokens.AUDIENCE,TOKENS.issuer(),-300)).statusCode());
        assertEquals(403,TestHttp.call(port,"GET",path,null,TOKENS.token("alice","Orders.Read")).statusCode());
    }
}
