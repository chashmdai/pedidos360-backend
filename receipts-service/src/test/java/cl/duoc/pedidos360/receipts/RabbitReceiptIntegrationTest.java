package cl.duoc.pedidos360.receipts;

import cl.duoc.pedidos360.messaging.OrderRegisteredV1;
import cl.duoc.pedidos360.receipts.application.ReceiptStore;
import cl.duoc.pedidos360.receipts.infrastructure.*;
import java.math.BigDecimal;
import java.nio.file.Path;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
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
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import tools.jackson.databind.json.JsonMapper;

class RabbitReceiptIntegrationTest {
    @Configuration @EnableRabbit static class ListenerSetup {}
    @TempDir static Path directory;
    static final String PASSWORD=UUID.randomUUID().toString();
    static final GenericContainer<?> BROKER=new GenericContainer<>("rabbitmq:4.2.9-management@sha256:1cca59efba1c7f3da7daae7ae1e08f70e174e5a09ecfb08f01305b440fabe9be")
        .withEnv("RABBITMQ_DEFAULT_USER","ep3-test").withEnv("RABBITMQ_DEFAULT_PASS",PASSWORD)
        .withEnv("RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS","+S 2:2").withExposedPorts(5672)
        .withLabel("Project","Pedidos360").withLabel("Purpose","ep3-test")
        .withCreateContainerCmdModifier(cmd->{cmd.withName("pedidos360-ep3-test-rabbit-"+UUID.randomUUID().toString().substring(0,8));cmd.getHostConfig().withMemory(768L*1024*1024);})
        .waitingFor(Wait.forLogMessage(".*Server startup complete.*",1)).withStartupTimeout(Duration.ofSeconds(120));
    static CachingConnectionFactory connection;
    static AnnotationConfigApplicationContext context;
    static RabbitTemplate rabbit;
    static FileReceiptStore files;
    static String queue="pedidos360.test.receipts",dlq="pedidos360.test.dlq";
    static final JsonMapper JSON=new JsonMapper();
    @BeforeAll static void start() throws Exception {
        BROKER.start();connection=new CachingConnectionFactory(BROKER.getHost(),BROKER.getMappedPort(5672));
        connection.setUsername("ep3-test");connection.setPassword(PASSWORD);
        var admin=new RabbitAdmin(connection);
        admin.declareExchange(new DirectExchange("pedidos360.test.events"));admin.declareExchange(new DirectExchange("pedidos360.test.errors"));
        admin.declareQueue(QueueBuilder.durable(queue).deadLetterExchange("pedidos360.test.errors").deadLetterRoutingKey("failed").build());
        admin.declareQueue(QueueBuilder.durable(dlq).build());
        admin.declareBinding(new Binding(queue,Binding.DestinationType.QUEUE,"pedidos360.test.events","registered",null));
        admin.declareBinding(new Binding(dlq,Binding.DestinationType.QUEUE,"pedidos360.test.errors","failed",null));
        files=new FileReceiptStore(directory.toString(),JSON);
        context=new AnnotationConfigApplicationContext();
        context.getEnvironment().getPropertySources().addFirst(new MapPropertySource("test",Map.of("pedidos.messaging.queue",queue)));
        context.register(ListenerSetup.class);
        context.registerBean("rabbitListenerContainerFactory",SimpleRabbitListenerContainerFactory.class,()->{
            var factory=new SimpleRabbitListenerContainerFactory();factory.setConnectionFactory(connection);
            factory.setAcknowledgeMode(AcknowledgeMode.MANUAL);factory.setPrefetchCount(1);return factory;
        });
        context.registerBean(ReceiptListener.class,()->new ReceiptListener(files,JSON,3,10));context.refresh();
        rabbit=new RabbitTemplate(connection);
    }
    @AfterAll static void stop() {
        if (context!=null) context.close();if (connection!=null) connection.destroy();BROKER.stop();
    }
    @Test void realBrokerRoutesConsumesAndDeadLettersMalformedMessage() throws Exception {
        var event=new OrderRegisteredV1(1,UUID.randomUUID(),UUID.randomUUID(),"test-tenant",Instant.now(),new BigDecimal("25.00"),"CLP",1);
        var props=new MessageProperties();props.setMessageId(event.eventId().toString());
        rabbit.send("pedidos360.test.events","registered",new Message(JSON.writeValueAsBytes(event),props));
        long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(15);
        while (files.findByTenant("test-tenant").isEmpty() && System.nanoTime()<deadline) Thread.sleep(50);
        assertEquals(1,files.findByTenant("test-tenant").size());
        rabbit.send("pedidos360.test.events","registered",new Message("{bad".getBytes(),new MessageProperties()));
        var failed=rabbit.receive(dlq,15000);assertNotNull(failed);
        assertTrue(failed.getMessageProperties().getHeaders().containsKey("x-death"));
        assertTrue(failed.getMessageProperties().getHeaders().get("x-death").toString().contains("rejected"));
        assertNull(rabbit.receive(queue,100));
    }
}
