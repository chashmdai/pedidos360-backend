package cl.duoc.pedidos360.rabbitadmin;
import java.time.Duration;
import java.util.*;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.*;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import tools.jackson.databind.json.JsonMapper;

/** Local signed fixture + real disposable broker; never presented as an Entra/cloud test. */
@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT)
class AdminRestIntegrationTest {
    static final TestTokens TOKENS=new TestTokens();
    static final String PASSWORD=UUID.randomUUID().toString();
    static final GenericContainer<?> BROKER=start();
    static GenericContainer<?> start() {
        var broker=new GenericContainer<>("rabbitmq:4.2.9-management@sha256:1cca59efba1c7f3da7daae7ae1e08f70e174e5a09ecfb08f01305b440fabe9be")
            .withEnv("RABBITMQ_DEFAULT_USER","ep4-test").withEnv("RABBITMQ_DEFAULT_PASS",PASSWORD)
            .withEnv("RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS","+S 1:1").withExposedPorts(15672)
            .withLabel("Project","Pedidos360").withLabel("Purpose","ep4-admin-test")
            .withCreateContainerCmdModifier(c->{c.withName("pedidos360-ep4-test-admin-"+UUID.randomUUID().toString().substring(0,8));c.getHostConfig().withMemory(512L*1024*1024);})
            .waitingFor(Wait.forHttp("/api/overview").forPort(15672).withBasicCredentials("ep4-test",PASSWORD)).withStartupTimeout(Duration.ofSeconds(120));
        broker.start();return broker;
    }
    @LocalServerPort int port;
    @DynamicPropertySource static void configure(DynamicPropertyRegistry r) {
        r.add("pedidos.security.tenant",()->"test-tenant");r.add("pedidos.security.client",()->"test-spa");
        r.add("pedidos.security.issuer",TOKENS::issuer);r.add("pedidos.security.audience",()->TestTokens.AUDIENCE);r.add("pedidos.security.jwks",()->TOKENS.issuer()+"/jwks");
        r.add("pedidos.rabbit-admin.url",()->"http://"+BROKER.getHost()+":"+BROKER.getMappedPort(15672));
        r.add("pedidos.rabbit-admin.vhost",()->"/");r.add("pedidos.rabbit-admin.username",()->"ep4-test");r.add("pedidos.rabbit-admin.password",()->PASSWORD);
    }
    String admin() { return TOKENS.withClaims("admin","Orders.Read",Map.of("roles",List.of("Admin"))); }
    @AfterAll static void close() { BROKER.stop();TOKENS.close(); }
    int call(String method,String path,String body) throws Exception { return TestHttp.call(port,method,"/api/v1/rabbit"+path,body,admin()).statusCode(); }
    @Test void restCrudAndMutablePolicyUpdatePreserveQueueIdentity() throws Exception {
        String name="pedidos360.lab.ep4-crud",exchange="pedidos360.lab.ep4-events";
        String queue="{\"name\":\""+name+"\",\"durable\":true,\"autoDelete\":false}";
        assertEquals(201,call("POST","/queues",queue));assertEquals(200,call("POST","/queues",queue));
        var before=TestHttp.call(port,"GET","/api/v1/rabbit/queues/"+name,null,admin());
        assertEquals(200,before.statusCode());
        assertEquals(200,call("PATCH","/queues/"+name+"/policy","{\"messageTtl\":60000,\"maxLength\":100}"));
        var updated=TestHttp.call(port,"PATCH","/api/v1/rabbit/queues/"+name+"/policy","{\"messageTtl\":120000,\"maxLength\":200}",admin());
        assertEquals(200,updated.statusCode());assertTrue(updated.body().contains("120000"));
        var after=TestHttp.call(port,"GET","/api/v1/rabbit/queues/"+name,null,admin());
        var json=new JsonMapper();assertEquals(json.readTree(before.body()).get("node"),json.readTree(after.body()).get("node"));
        assertEquals(409,call("POST","/queues",queue.replace("true","false")));
        assertEquals(201,call("POST","/exchanges","{\"name\":\""+exchange+"\",\"type\":\"topic\",\"durable\":true,\"autoDelete\":false}"));
        String binding="{\"exchange\":\""+exchange+"\",\"queue\":\""+name+"\",\"routingKey\":\"order.#\"}";
        assertEquals(201,call("POST","/bindings",binding));assertEquals(200,call("POST","/bindings",binding));
        assertEquals(204,call("DELETE","/bindings",binding));assertEquals(204,call("DELETE","/queues/"+name,null));
        assertEquals(404,call("GET","/queues/"+name,null));assertEquals(204,call("DELETE","/exchanges/"+exchange,null));
    }
    @Test void validatesPolicyAndRejectsBusinessNamespaceAndImmutableArguments() throws Exception {
        assertEquals(400,call("POST","/queues","{\"name\":\"\",\"durable\":true,\"autoDelete\":false}"));
        assertEquals(403,call("PATCH","/queues/pedidos360.sales.order-registered.v1/policy","{\"maxLength\":100}"));
        String name="pedidos360.lab.ep4-immutable";
        assertEquals(201,call("POST","/queues","{\"name\":\""+name+"\",\"durable\":true,\"autoDelete\":false,\"messageTtl\":60000}"));
        assertEquals(400,call("PATCH","/queues/"+name+"/policy","{}"));
        assertEquals(400,call("PATCH","/queues/"+name+"/policy","{\"maxLength\":10001}"));
        assertEquals(409,call("PATCH","/queues/"+name+"/policy","{\"messageTtl\":120000}"));
        assertEquals(204,call("DELETE","/queues/"+name,null));
    }
    @Test void requiresValidJwtAdminAndScope() throws Exception {
        String path="/api/v1/rabbit/queues/pedidos360.lab.denied";
        assertEquals(401,TestHttp.call(port,"GET",path,null,null).statusCode());
        assertEquals(403,TestHttp.call(port,"GET",path,null,TOKENS.token("user","Orders.Read")).statusCode());
        assertEquals(403,TestHttp.call(port,"GET",path,null,TOKENS.withClaims("admin","Catalog.Read",Map.of("roles",List.of("Admin")))).statusCode());
    }
}
