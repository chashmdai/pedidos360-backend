package cl.duoc.pedidos360.sales;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.*;

import cl.duoc.pedidos360.kafka.OrderRegisteredStreamV1;
import cl.duoc.pedidos360.kafka.ProductSalesMetricV1;
import cl.duoc.pedidos360.sales.application.LiveSalesView;
import cl.duoc.pedidos360.sales.application.MetricPublisher;
import cl.duoc.pedidos360.sales.domain.DailyProductSales;
import cl.duoc.pedidos360.sales.infrastructure.streaming.KafkaMetricPublisher;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.test.utils.ContainerTestUtils;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * sales-stream-service against real Kafka and MySQL: three groups, idempotency by eventId, version
 * discard, DLT without retries for contract/deserialization errors, retries with backoff for transient
 * errors, rebuild of the view from the compacted topic and the protected live endpoint filtered by tid.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ExtendWith(OutputCaptureExtension.class)
@DirtiesContext
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class SalesStreamIntegrationTest {
    static final TestDatabase DB = new TestDatabase();
    static final TestKafka KAFKA = new TestKafka();
    static final TestTokens TOKENS = new TestTokens();
    static final String ORDERS = "pedidos360.orders.registered.v1";
    static final String METRICS = "pedidos360.sales.product-metrics.v1";
    static final String TENANT = "test-tenant";
    static final JsonMapper JSON = new JsonMapper();
    static final UUID COFFEE = UUID.fromString("10000000-0000-0000-0000-000000000001");
    static final UUID MUG = UUID.fromString("10000000-0000-0000-0000-000000000002");
    static final Map<UUID, AtomicInteger> FAILURES = new ConcurrentHashMap<>();
    static OrderRegisteredStreamV1 first;

    @DynamicPropertySource static void configure(DynamicPropertyRegistry r) {
        DB.properties(r); KAFKA.properties(r);
        r.add("pedidos.security.issuer", TOKENS::issuer); r.add("pedidos.security.jwks", () -> TOKENS.issuer() + "/jwks");
        r.add("pedidos.security.audience", () -> TestTokens.AUDIENCE);
        r.add("pedidos.security.tenant", () -> TENANT); r.add("pedidos.security.client", () -> "test-spa");
    }

    /** Fails publication for products registered in FAILURES (a transient, post-commit error). */
    @TestConfiguration static class FlakyPublisher {
        @Bean @Primary MetricPublisher flaky(KafkaMetricPublisher real) {
            return states -> {
                for (var s : states) {
                    var remaining = FAILURES.get(s.key().productId());
                    if (remaining != null && remaining.getAndDecrement() > 0) throw new IllegalStateException("simulated broker timeout");
                }
                real.publish(states);
            };
        }
    }

    @Autowired JdbcTemplate jdbc;
    @Autowired LiveSalesView view;
    @Autowired KafkaListenerEndpointRegistry registry;
    @LocalServerPort int port;

    @BeforeEach void waitForAssignments() {
        // The monitor starts at "latest": wait until every group owns its three partitions.
        for (var id : List.of("sales-aggregator", "order-monitor", "sales-dashboard")) {
            ContainerTestUtils.waitForAssignment(registry.getListenerContainer(id), 3);
        }
    }

    @AfterAll static void close(@Autowired org.springframework.context.ConfigurableApplicationContext context) {
        context.stop();
        KAFKA.close(); DB.close(); TOKENS.close();
    }

    // ---------- helpers ----------

    static OrderRegisteredStreamV1 event(String tenant, Instant at, Object... productQuantityPrice) {
        var items = new ArrayList<OrderRegisteredStreamV1.Item>();
        for (int i = 0; i < productQuantityPrice.length; i += 4) {
            var unit = new BigDecimal((String) productQuantityPrice[i + 3]);
            int quantity = (Integer) productQuantityPrice[i + 2];
            items.add(new OrderRegisteredStreamV1.Item((UUID) productQuantityPrice[i], (String) productQuantityPrice[i + 1], quantity, unit,
                    unit.multiply(BigDecimal.valueOf(quantity))));
        }
        var total = items.stream().map(OrderRegisteredStreamV1.Item::lineTotal).reduce(BigDecimal.ZERO, BigDecimal::add);
        return new OrderRegisteredStreamV1(1, UUID.randomUUID(), UUID.randomUUID(), tenant, at, "CLP", total, items.size(), items);
    }

    static void send(String topic, String key, String value) {
        var config = Map.<String, Object>of("bootstrap.servers", KAFKA.bootstrap(), "acks", "all");
        try (var producer = new KafkaProducer<>(config, new StringSerializer(), new StringSerializer())) {
            producer.send(new ProducerRecord<>(topic, key, value)).get();
        } catch (Exception e) { throw new IllegalStateException(e); }
    }

    static void send(OrderRegisteredStreamV1 event) { send(ORDERS, event.orderId().toString(), JSON.writeValueAsString(event)); }

    Map<String, Object> row(UUID product, String tenant) {
        var rows = jdbc.queryForList("SELECT units_sold,orders_count,revenue,version,last_event_id FROM product_sales_daily "
                + "WHERE tenant_id=? AND product_id=? AND business_date=? AND currency='CLP'", tenant, product.toString(), LocalDate.now(ZoneOffset.UTC));
        return rows.isEmpty() ? null : rows.getFirst();
    }

    static long number(Map<String, Object> row, String column) { return ((Number) row.get(column)).longValue(); }

    Optional<DailyProductSales> viewed(UUID product) {
        return view.snapshot(TENANT).products().stream().filter(p -> p.key().productId().equals(product)).findFirst();
    }

    /** DLT record written by the aggregator group (every failing group writes its own copy, tagged by this header). */
    static ConsumerRecord<String, String> aggregatorDlt(java.util.function.Predicate<ConsumerRecord<String, String>> match) {
        return KAFKA.find(ORDERS + ".DLT", r -> "pedidos360-sales-aggregator".equals(header(r, "kafka_dlt-original-consumer-group")) && match.test(r),
                Duration.ofSeconds(30));
    }

    static String header(ConsumerRecord<String, String> record, String name) {
        var header = record.headers().lastHeader(name);
        return header == null ? null : new String(header.value(), StandardCharsets.UTF_8);
    }

    static int intHeader(ConsumerRecord<String, String> record, String name) {
        return java.nio.ByteBuffer.wrap(record.headers().lastHeader(name).value()).getInt();
    }

    static long longHeader(ConsumerRecord<String, String> record, String name) {
        return java.nio.ByteBuffer.wrap(record.headers().lastHeader(name).value()).getLong();
    }

    // ---------- tests ----------

    @Test @Order(1)
    void orderIsAggregatedPublishedAsMetricMaterializedAndRaisesAlert(CapturedOutput output) {
        first = event(TENANT, Instant.now(), COFFEE, "Café de especialidad", 2, "25000.00", MUG, "Taza de cerámica", 1, "5990.00");
        var foreign = event("other-tenant", Instant.now(), COFFEE, "Café de especialidad", 7, "1000.00");
        send(first); send(foreign);

        await().atMost(Duration.ofSeconds(30)).until(() -> row(MUG, TENANT) != null && viewed(MUG).isPresent());
        var coffee = row(COFFEE, TENANT);
        assertEquals(2, number(coffee, "units_sold")); assertEquals(1, number(coffee, "orders_count"));
        assertEquals(0, new BigDecimal("50000.00").compareTo((BigDecimal) coffee.get("revenue")));
        assertEquals(1, number(coffee, "version"));
        assertEquals(first.eventId().toString(), coffee.get("last_event_id"));
        assertEquals(1, jdbc.queryForObject("SELECT COUNT(*) FROM processed_stream_event WHERE event_id=? AND consumer_group='pedidos360-sales-aggregator'",
                Integer.class, first.eventId().toString()));

        // Complete state on the compacted topic, keyed tenantId:productId:date:currency, without type headers.
        String key = TENANT + ":" + COFFEE + ":" + LocalDate.now(ZoneOffset.UTC) + ":CLP";
        var metric = KAFKA.read(METRICS, 3, Duration.ofSeconds(20)).stream().filter(r -> key.equals(r.key())).findFirst().orElseThrow();
        assertFalse(metric.headers().iterator().hasNext());
        var published = JSON.readValue(metric.value(), ProductSalesMetricV1.class);
        assertEquals(key, published.metricKey()); assertEquals(1, published.version()); assertEquals(first.eventId(), published.lastEventId());

        await().atMost(Duration.ofSeconds(20)).until(() -> view.snapshot(TENANT).alerts().stream().anyMatch(a -> a.orderId().equals(first.orderId())));
        assertTrue(output.getOut().contains("ORDER_ALERT eventId=" + first.eventId() + " orderId=" + first.orderId() + " reasons=[HIGH_VALUE] total=55990.00"));
        assertTrue(output.getOut().contains("CONSUME_OK eventId=" + first.eventId() + " group=pedidos360-sales-aggregator topic=" + ORDERS));
        assertTrue(output.getOut().contains("CONSUME_OK eventId=" + first.eventId() + " group=pedidos360-order-monitor topic=" + ORDERS));
        assertTrue(output.getOut().contains("group=pedidos360-sales-dashboard topic=" + METRICS));
        assertEquals(2, viewed(COFFEE).orElseThrow().unitsSold(), "foreign tenant does not leak into this tenant's view");
    }

    @Test @Order(2)
    void duplicateEventIdChangesNothingAndOlderVersionsAreDiscarded(CapturedOutput output) {
        send(first);   // same payload, same key: a redelivery
        await().atMost(Duration.ofSeconds(20)).until(() -> output.getOut().contains("CONSUME_DUPLICATE eventId=" + first.eventId()
                + " group=pedidos360-sales-aggregator"));
        assertEquals(1, number(row(COFFEE, TENANT), "version"), "accumulator unchanged");
        assertEquals(2, number(row(COFFEE, TENANT), "units_sold"));

        var second = event(TENANT, Instant.now(), COFFEE, "Café de especialidad", 1, "25000.00");
        send(second);
        await().atMost(Duration.ofSeconds(20)).until(() -> viewed(COFFEE).map(DailyProductSales::version).orElse(0L) == 2);
        assertEquals(3, viewed(COFFEE).orElseThrow().unitsSold());
        assertEquals(2, viewed(COFFEE).orElseThrow().ordersCount());

        // A stale state (version 1) arriving after version 2 must be ignored by the dashboard.
        var stale = new ProductSalesMetricV1(1, TENANT + ":" + COFFEE + ":" + LocalDate.now(ZoneOffset.UTC) + ":CLP", TENANT, COFFEE,
                "Café de especialidad", LocalDate.now(ZoneOffset.UTC), "CLP", 2, 1, new BigDecimal("50000.00"), 1, first.eventId(), Instant.now());
        send(METRICS, stale.metricKey(), JSON.writeValueAsString(stale));
        await().atMost(Duration.ofSeconds(20)).until(() -> output.getOut().contains("STALE_VERSION_DISCARDED version=1"));
        assertEquals(2, viewed(COFFEE).orElseThrow().version());
        assertEquals(3, viewed(COFFEE).orElseThrow().unitsSold());
    }

    @Test @Order(3)
    void invalidJsonGoesToDltWithoutRetriesAndThePartitionKeepsFlowing(CapturedOutput output) {
        var next = event(TENANT, Instant.now(), MUG, "Taza de cerámica", 1, "5990.00");
        String key = next.orderId().toString();   // same key => same partition as the valid event that follows
        send(ORDERS, key, "{not json");
        send(next);

        await().atMost(Duration.ofSeconds(30)).until(() -> number(row(MUG, TENANT), "units_sold") == 2);
        var failed = aggregatorDlt(r -> key.equals(r.key()) && "{not json".equals(r.value()));
        assertEquals(ORDERS, header(failed, "kafka_dlt-original-topic"));
        int partition = intHeader(failed, "kafka_dlt-original-partition");
        assertEquals(partition, failed.partition(), "the DLT keeps the original partition");
        long offset = longHeader(failed, "kafka_dlt-original-offset");
        assertNotNull(header(failed, "kafka_dlt-exception-fqcn"));
        assertNotNull(header(failed, "kafka_dlt-exception-message"));
        String context = "group=pedidos360-sales-aggregator topic=" + ORDERS + " partition=" + partition + " offset=" + offset;
        await().atMost(Duration.ofSeconds(10)).until(() -> output.getOut().contains("CONSUME_DLT eventId=unknown " + context + " code=DESERIALIZATION_FAILED retried=false"));
        assertFalse(output.getOut().contains("CONSUME_RETRY eventId=unknown " + context), "no retries for undeserializable payloads");
        // The monitor group reads the same partition independently and dead-letters its own copy.
        assertNotNull(KAFKA.find(ORDERS + ".DLT", r -> key.equals(r.key()) && "pedidos360-order-monitor".equals(header(r, "kafka_dlt-original-consumer-group")),
                Duration.ofSeconds(30)));
    }

    @Test @Order(4)
    void contractViolationGoesToDltImmediately(CapturedOutput output) {
        var valid = event(TENANT, Instant.now(), MUG, "Taza de cerámica", 1, "5990.00");
        String invalid = JSON.writeValueAsString(valid).replace("\"schemaVersion\":1", "\"schemaVersion\":2");
        send(ORDERS, valid.orderId().toString(), invalid);
        var failed = aggregatorDlt(r -> invalid.equals(r.value()));
        String context = "eventId=" + valid.eventId() + " group=pedidos360-sales-aggregator topic=" + ORDERS
                + " partition=" + intHeader(failed, "kafka_dlt-original-partition") + " offset=" + longHeader(failed, "kafka_dlt-original-offset");
        await().atMost(Duration.ofSeconds(10)).until(() -> output.getOut().contains("CONSUME_DLT " + context));
        var line = output.getOut().lines().filter(l -> l.contains("CONSUME_DLT " + context)).findFirst().orElseThrow();
        assertTrue(line.contains("retried=false"), line);
        assertTrue(line.contains("code=CONTRACT_INVALID") || line.contains("code=DESERIALIZATION_FAILED"), line);
        assertFalse(output.getOut().contains("CONSUME_RETRY " + context));
        assertNull(jdbc.queryForObject("SELECT MAX(event_id) FROM processed_stream_event WHERE event_id=?", String.class, valid.eventId().toString()));
    }

    @Test @Order(5)
    void transientFailureIsRetriedWithBackoffAndCountedOnce(CapturedOutput output) {
        var flaky = UUID.randomUUID();
        FAILURES.put(flaky, new AtomicInteger(2));   // attempts 1 and 2 fail after commit, attempt 3 succeeds
        var event = event(TENANT, Instant.now(), flaky, "Producto inestable", 4, "1000.00");
        long started = System.nanoTime();
        send(event);
        String prefix = "eventId=" + event.eventId() + " group=pedidos360-sales-aggregator";
        await().atMost(Duration.ofSeconds(30)).until(() -> output.getOut().contains("CONSUME_OK " + prefix) && output.getOut().contains("result=METRICS_REPUBLISHED"));
        assertTrue(Duration.ofNanos(System.nanoTime() - started).toMillis() >= 3000, "backoff 1 s + 2 s");
        assertTrue(output.getOut().contains("CONSUME_RETRY " + prefix) && output.getOut().contains("attempt=1 code=TRANSIENT_IllegalStateException"));
        assertTrue(output.getOut().lines().anyMatch(l -> l.contains("CONSUME_RETRY " + prefix) && l.contains("attempt=2 ")));
        var row = row(flaky, TENANT);
        assertEquals(4, number(row, "units_sold"), "applied once despite three deliveries");
        assertEquals(1, number(row, "version"));
        await().atMost(Duration.ofSeconds(20)).until(() -> viewed(flaky).isPresent());
    }

    @Test @Order(6)
    void exhaustedRetriesGoToDlt(CapturedOutput output) {
        var broken = UUID.randomUUID();
        FAILURES.put(broken, new AtomicInteger(Integer.MAX_VALUE));
        var event = event(TENANT, Instant.now(), broken, "Producto sin publicación", 1, "10.00");
        send(event);
        var failed = aggregatorDlt(r -> event.orderId().toString().equals(r.key()));
        assertEquals(event, JSON.readValue(failed.value(), OrderRegisteredStreamV1.class), "JSON DTO preserved in the DLT");
        String prefix = "CONSUME_DLT eventId=" + event.eventId() + " group=pedidos360-sales-aggregator";
        await().atMost(Duration.ofSeconds(10)).until(() -> output.getOut().contains(prefix));
        assertTrue(output.getOut().lines().anyMatch(l -> l.contains(prefix) && l.contains("code=TRANSIENT_IllegalStateException retried=true")));
        assertEquals(2, output.getOut().lines().filter(l -> l.contains("CONSUME_RETRY eventId=" + event.eventId())).count(), "three attempts in total");
        FAILURES.remove(broken);
    }

    @Test @Order(7)
    void consumerGroupsDistributePartitions() throws Exception {
        try (var admin = AdminClient.create(Map.of(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG, KAFKA.bootstrap()))) {
            var groups = admin.describeConsumerGroups(List.of("pedidos360-sales-aggregator", "pedidos360-order-monitor", "pedidos360-sales-dashboard"))
                    .all().get();
            var aggregator = groups.get("pedidos360-sales-aggregator").members();
            assertEquals(3, aggregator.size(), "three consumers in the aggregator");
            aggregator.forEach(m -> assertEquals(1, m.assignment().topicPartitions().size(), "one partition each"));
            for (var group : List.of("pedidos360-order-monitor", "pedidos360-sales-dashboard")) {
                var members = groups.get(group).members();
                assertEquals(1, members.size(), group);
                assertEquals(3, members.iterator().next().assignment().topicPartitions().size(), group);
            }
            for (var group : groups.values()) assertEquals("cooperative-sticky", group.partitionAssignor(), group.groupId());
        }
    }

    @Test @Order(8)
    void dashboardRebuildsTheViewFromTheCompactedTopic(CapturedOutput output) {
        var before = view.snapshot(TENANT).products();
        assertFalse(before.isEmpty());
        var container = registry.getListenerContainer("sales-dashboard");
        container.stop();
        view.clearMetrics();
        assertTrue(view.snapshot(TENANT).products().isEmpty());
        container.start();
        await().atMost(Duration.ofSeconds(30)).until(() -> view.snapshot(TENANT).products().equals(before));
        assertTrue(output.getOut().contains("DASHBOARD_REBUILD group=pedidos360-sales-dashboard"));
    }

    @Test @Order(9)
    void liveEndpointRequiresOrdersReadAndOnlyShowsTheTokenTenant() throws Exception {
        String path = "/api/v1/ventas/en-vivo";
        assertEquals(401, TestHttp.call(port, "GET", path, null, null).statusCode());
        assertEquals(401, TestHttp.call(port, "GET", path, null, TOKENS.withClaims("alice", "Orders.Read", Map.of("tid", "other-tenant"))).statusCode(),
                "a token from another tenant is rejected");
        assertEquals(403, TestHttp.call(port, "GET", path, null, TOKENS.token("alice", "Catalog.Read")).statusCode());
        var response = TestHttp.call(port, "GET", path, null, TOKENS.token("alice", "Orders.Read"));
        assertEquals(200, response.statusCode(), response.body());
        assertTrue(response.headers().firstValue("Cache-Control").orElseThrow().contains("no-store"));
        var body = JSON.readTree(response.body());
        assertEquals(LocalDate.now(ZoneOffset.UTC).toString(), body.get("fecha").asString());
        var coffee = stream(body.get("productos")).filter(p -> p.get("productoId").asString().equals(COFFEE.toString())).findFirst().orElseThrow();
        assertEquals(3, coffee.get("unidades").asInt(), "own tenant only: the foreign tenant's 7 units are excluded");
        assertEquals("CLP", coffee.get("moneda").asString());
        assertEquals(2, coffee.get("version").asInt());
        var alert = stream(body.get("alertas")).filter(a -> a.get("pedidoId").asString().equals(first.orderId().toString())).findFirst().orElseThrow();
        assertEquals("ALTO_VALOR", alert.get("motivos").get(0).asString());
        assertFalse(response.body().contains("alice"), "no identity data");

        // The response matches contracts/live-sales-response-v1.schema.json (fields and required lists).
        var schema = JSON.readTree(Path.of("..", "contracts", "live-sales-response-v1.schema.json").toFile());
        assertEquals(names(schema.get("required")), new TreeSet<>(body.propertyNames()));
        var items = schema.get("properties");
        assertEquals(names(items.get("productos").get("items").get("required")), new TreeSet<>(coffee.propertyNames()));
        assertEquals(names(items.get("alertas").get("items").get("required")), new TreeSet<>(alert.propertyNames()));
    }

    @Autowired org.springframework.context.ApplicationContext context;

    @Test @Order(10)
    void consumerConfigurationMatchesTables11And12() {
        record Expected(String factory, String group, String reset, int concurrency, Class<?> type) {}
        for (var e : List.of(
                new Expected("aggregatorContainerFactory", "pedidos360-sales-aggregator", "earliest", 3, OrderRegisteredStreamV1.class),
                new Expected("monitorContainerFactory", "pedidos360-order-monitor", "latest", 1, OrderRegisteredStreamV1.class),
                new Expected("dashboardContainerFactory", "pedidos360-sales-dashboard", "earliest", 1, ProductSalesMetricV1.class))) {
            var factory = context.getBean(e.factory(), org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory.class);
            var props = factory.getConsumerFactory().getConfigurationProperties();
            assertEquals(e.group(), props.get("group.id"), e.factory());
            assertEquals(e.reset(), props.get("auto.offset.reset"), e.factory());
            assertEquals(org.apache.kafka.common.serialization.StringDeserializer.class.getName(), String.valueOf(props.get("key.deserializer")).replace("class ", ""));
            assertEquals(org.springframework.kafka.support.serializer.ErrorHandlingDeserializer.class, props.get("value.deserializer"));
            assertEquals(org.springframework.kafka.support.serializer.JacksonJsonDeserializer.class, props.get("spring.deserializer.value.delegate.class"));
            assertEquals(e.type().getName(), props.get("spring.json.value.default.type"));
            assertEquals(false, props.get("spring.json.use.type.headers"));
            assertEquals(false, props.get("enable.auto.commit"));
            assertEquals(50, props.get("max.poll.records"));
            assertEquals("300000", String.valueOf(props.get("max.poll.interval.ms")));
            assertEquals("org.apache.kafka.clients.consumer.CooperativeStickyAssignor", String.valueOf(props.get("partition.assignment.strategy")));
            assertEquals(org.springframework.kafka.listener.ContainerProperties.AckMode.RECORD, factory.getContainerProperties().getAckMode());
            var container = registry.getListenerContainer(e.factory().replace("ContainerFactory", "").replace("aggregator", "sales-aggregator")
                    .replace("monitor", "order-monitor").replace("dashboard", "sales-dashboard"));
            assertEquals(e.concurrency(), ((org.springframework.kafka.listener.ConcurrentMessageListenerContainer<?, ?>) container).getConcurrency(), e.factory());
        }
    }

    static java.util.stream.Stream<JsonNode> stream(JsonNode array) {
        var list = new ArrayList<JsonNode>(); array.forEach(list::add); return list.stream();
    }

    static Set<String> names(JsonNode array) { var set = new TreeSet<String>(); array.forEach(n -> set.add(n.asString())); return set; }
}
