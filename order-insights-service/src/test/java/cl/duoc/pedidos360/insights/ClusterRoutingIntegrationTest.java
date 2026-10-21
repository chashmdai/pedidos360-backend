package cl.duoc.pedidos360.insights;
import cl.duoc.pedidos360.insights.audit.AuditListener;
import cl.duoc.pedidos360.insights.sales.SalesListener;
import cl.duoc.pedidos360.insights.infrastructure.FileProjectionStore;
import cl.duoc.pedidos360.messaging.*;
import java.math.BigDecimal;
import java.nio.file.Path;
import java.time.*;
import java.util.*;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;
import org.springframework.amqp.core.*;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.amqp.rabbit.core.*;
import org.springframework.context.annotation.*;
import org.springframework.core.env.MapPropertySource;
import org.testcontainers.containers.*;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.images.builder.Transferable;
import tools.jackson.databind.json.JsonMapper;

class ClusterRoutingIntegrationTest {
    @Configuration @EnableRabbit static class Listeners {}
    @TempDir static Path directory;
    static final String PASSWORD=UUID.randomUUID().toString(), COOKIE=UUID.randomUUID().toString().replace("-","");
    static final Network NETWORK=Network.newNetwork();
    static GenericContainer<?> node(String name) {
        return new GenericContainer<>("rabbitmq:4.2.9-management@sha256:1cca59efba1c7f3da7daae7ae1e08f70e174e5a09ecfb08f01305b440fabe9be")
            .withNetwork(NETWORK).withNetworkAliases(name).withCreateContainerCmdModifier(c->{c.withHostName(name);c.withName("pedidos360-ep4-test-"+name+"-"+UUID.randomUUID().toString().substring(0,8));c.getHostConfig().withMemory(512L*1024*1024);})
            .withEnv("RABBITMQ_NODENAME","rabbit@"+name).withEnv("RABBITMQ_DEFAULT_USER","ep4-test").withEnv("RABBITMQ_DEFAULT_PASS",PASSWORD)
            .withCopyToContainer(Transferable.of(COOKIE,0400),"/var/lib/rabbitmq/.erlang.cookie")
            .withEnv("RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS","+S 1:1").withExposedPorts(5672)
            .withLabel("Project","Pedidos360").withLabel("Purpose","ep4-test")
            .waitingFor(Wait.forLogMessage(".*Server startup complete.*",1)).withStartupTimeout(Duration.ofSeconds(120));
    }
    static GenericContainer<?> a=node("ep4-a"),b=node("ep4-b");
    static CachingConnectionFactory consumer,producer;
    static AnnotationConfigApplicationContext context;
    static RabbitTemplate rabbit;
    static MessagingProperties names;
    static InsightsTopology.Names insights;
    static final JsonMapper JSON=new JsonMapper();
    static FileProjectionStore audit,sales;
    @BeforeAll static void start() throws Exception {
        a.start();b.start();
        var join=b.execInContainer("rabbitmqctl","join_cluster","rabbit@ep4-a");assertEquals(0,join.getExitCode(),join.getStderr());
        var cluster=a.execInContainer("rabbitmqctl","cluster_status","--formatter=json");
        assertEquals(0,cluster.getExitCode());assertTrue(cluster.getStdout().contains("rabbit@ep4-a"));assertTrue(cluster.getStdout().contains("rabbit@ep4-b"));
        consumer=connection(a);producer=connection(b);
        context=new AnnotationConfigApplicationContext();
        context.getEnvironment().getPropertySources().addFirst(new MapPropertySource("ep4",Map.of("pedidos.messaging.ep4-enabled","true","RABBIT_USER","ep4-test","RABBIT_PASSWORD",PASSWORD)));
        context.register(MessagingConfiguration.class,Listeners.class);
        context.registerBean("rabbitListenerContainerFactory",SimpleRabbitListenerContainerFactory.class,()->{
            var factory=new SimpleRabbitListenerContainerFactory();factory.setConnectionFactory(consumer);factory.setAcknowledgeMode(AcknowledgeMode.MANUAL);factory.setPrefetchCount(1);return factory;
        });
        audit=new FileProjectionStore(directory.resolve("audit"),JSON);sales=new FileProjectionStore(directory.resolve("sales"),JSON);
        context.registerBean(AuditListener.class,()->new AuditListener(audit,JSON,3,10));context.registerBean(SalesListener.class,()->new SalesListener(sales,JSON,3,10));
        // Declare the exact production beans before starting consumers.
        context.addBeanFactoryPostProcessor(factory -> {});
        context.registerBean("connectionFactory",CachingConnectionFactory.class,()->consumer);
        context.registerBean(RabbitAdmin.class,()->new RabbitAdmin(consumer));context.refresh();
        names=context.getBean(MessagingProperties.class);insights=context.getBean(InsightsTopology.Names.class);
        context.getBean(RabbitAdmin.class).initialize();rabbit=new RabbitTemplate(producer);
    }
    static CachingConnectionFactory connection(GenericContainer<?> node) {
        var factory=new CachingConnectionFactory(node.getHost(),node.getMappedPort(5672));factory.setUsername("ep4-test");factory.setPassword(PASSWORD);return factory;
    }
    @AfterAll static void stop() {
        if(context!=null)context.close();if(consumer!=null)consumer.destroy();if(producer!=null)producer.destroy();
        b.stop();a.stop();NETWORK.close();
    }
    static Message message(OrderRegisteredV1 event) {
        var props=new MessageProperties();props.setMessageId(event.eventId().toString());props.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
        return new Message(JSON.writeValueAsBytes(event),props);
    }
    @Test void crossNodeDirectTopicRoutesThreeQueuesWithIndependentDeadLettersAndIdempotentEffects() throws Exception {
        var event=new OrderRegisteredV1(1,UUID.randomUUID(),UUID.randomUUID(),"ep4-test",Instant.now(),new BigDecimal("30970.00"),"CLP",2);
        rabbit.send(names.exchange(),names.routingKey(),message(event));
        long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(20);
        while((audit.findByTenant("ep4-test").isEmpty() || sales.findByTenant("ep4-test").isEmpty()) && System.nanoTime()<deadline)Thread.sleep(50);
        assertEquals(1,audit.findByTenant("ep4-test").size());assertEquals(1,sales.findByTenant("ep4-test").size());
        var receipt=rabbit.receive(names.queue(),10000);assertNotNull(receipt);assertEquals(event.eventId().toString(),receipt.getMessageProperties().getMessageId());
        rabbit.send(names.exchange(),names.routingKey(),message(event));
        Thread.sleep(300);assertEquals(1,audit.findByTenant("ep4-test").size());assertEquals(1,sales.findByTenant("ep4-test").size());
        assertNotNull(rabbit.receive(names.queue(),10000));
        rabbit.send(insights.topicExchange(),"order.cancelled.v1",message(event));
        assertNull(rabbit.receive(insights.auditQueue(),100));assertNull(rabbit.receive(insights.salesQueue(),100));
        rabbit.send(names.exchange(),names.routingKey(),new Message("{invalid".getBytes(),new MessageProperties()));
        for(String dlq:List.of(insights.auditDeadQueue(),insights.salesDeadQueue())) {
            var failed=rabbit.receive(dlq,15000);assertNotNull(failed);assertTrue(failed.getMessageProperties().getHeaders().get("x-death").toString().contains("rejected"));
        }
        // The receipt listener itself is already covered by the EP3 Testcontainers integration test.
        try(var channel=producer.createConnection().createChannel(false)) {
            var invalid=channel.basicGet(names.queue(),false);assertNotNull(invalid);channel.basicNack(invalid.getEnvelope().getDeliveryTag(),false,false);
        }
        var receiptFailure=rabbit.receive(names.deadQueue(),10000);assertNotNull(receiptFailure);
        assertTrue(receiptFailure.getMessageProperties().getHeaders().get("x-death").toString().contains("rejected"));
    }
}
