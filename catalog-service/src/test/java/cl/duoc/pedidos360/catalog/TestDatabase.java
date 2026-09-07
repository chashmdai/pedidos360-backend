package cl.duoc.pedidos360.catalog;
import java.util.UUID;
import org.testcontainers.containers.Network;
import org.testcontainers.mysql.MySQLContainer;
import org.testcontainers.utility.DockerImageName;
import org.springframework.test.context.DynamicPropertyRegistry;

/** Only creates resources carrying a Pedidos360 name/label; no shared database. */
final class TestDatabase implements AutoCloseable {
    private final String suffix=UUID.randomUUID().toString().substring(0,8);
    private final Network network=Network.builder().createNetworkCmdModifier(cmd ->
        cmd.withName("pedidos360-test-catalog-"+suffix).withLabels(java.util.Map.of("Project","Pedidos360","Purpose","test"))).build();
    private final MySQLContainer mysql=new MySQLContainer(DockerImageName.parse("mysql:8.4.11@sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb").asCompatibleSubstituteFor("mysql"))
        .withDatabaseName("pedidos360_test_catalog").withUsername("pedidos360_test").withPassword(UUID.randomUUID().toString())
        .withNetwork(network).withLabel("Project","Pedidos360").withLabel("Purpose","test")
        .withCreateContainerCmdModifier(cmd -> {
            cmd.withName("pedidos360-test-mysql-catalog-"+suffix);
            cmd.getHostConfig().withMemory(768L*1024*1024);
        });
    TestDatabase() { try { mysql.start(); } catch (RuntimeException error) { close(); throw error; } }
    void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url",mysql::getJdbcUrl);
        registry.add("spring.datasource.username",mysql::getUsername);
        registry.add("spring.datasource.password",mysql::getPassword);
        registry.add("spring.flyway.url",mysql::getJdbcUrl);
        registry.add("spring.flyway.user",mysql::getUsername);
        registry.add("spring.flyway.password",mysql::getPassword);
    }
    public void close() { try { mysql.stop(); } finally { network.close(); } }
}
