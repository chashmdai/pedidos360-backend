package cl.duoc.pedidos360.kafka;

import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import org.apache.kafka.common.header.internals.RecordHeaders;
import org.junit.jupiter.api.Test;
import org.springframework.kafka.support.serializer.JacksonJsonDeserializer;
import org.springframework.kafka.support.serializer.JacksonJsonSerializer;

class StreamContractsTest {
    static final UUID P1 = UUID.fromString("10000000-0000-0000-0000-000000000001");
    static final UUID P2 = UUID.fromString("10000000-0000-0000-0000-000000000002");

    static OrderRegisteredStreamV1.Item item(UUID product, int quantity, String price) {
        var unit = new BigDecimal(price);
        return new OrderRegisteredStreamV1.Item(product, "Producto", quantity, unit, unit.multiply(BigDecimal.valueOf(quantity)));
    }

    static OrderRegisteredStreamV1 event(int schemaVersion, String total, List<OrderRegisteredStreamV1.Item> items) {
        return new OrderRegisteredStreamV1(schemaVersion, UUID.randomUUID(), UUID.randomUUID(), "tenant",
                Instant.parse("2026-11-24T14:05:12.345678Z"), "CLP", new BigDecimal(total), items.size(), items);
    }

    @Test void validOrderEventMatchesReportExample() {
        var event = event(1, "30970.00", List.of(item(P1, 1, "18990.00"), item(P2, 2, "5990.00")));
        assertEquals(2, event.itemCount());
        assertThrows(UnsupportedOperationException.class, () -> event.items().add(item(P1, 1, "1.00")), "items are immutable");
    }

    @Test void amountsAreCanonicalizedToTwoDecimals() {
        // MySQL JSON columns return 8990.0 for 8990.00; the wire format always carries two decimals.
        var item = new OrderRegisteredStreamV1.Item(P1, "Producto", 2, new BigDecimal("8990.0"), new BigDecimal("17980"));
        assertEquals("8990.00", item.unitPrice().toPlainString());
        assertEquals("17980.00", item.lineTotal().toPlainString());
        var event = new OrderRegisteredStreamV1(1, UUID.randomUUID(), UUID.randomUUID(), "tenant", Instant.now(), "CLP",
                new BigDecimal("17980.0"), 1, List.of(item));
        assertEquals("17980.00", event.total().toPlainString());
    }

    @Test void orderEventRejectsContractViolations() {
        var ok = List.of(item(P1, 1, "18990.00"));
        assertThrows(StreamContractException.class, () -> event(2, "18990.00", ok), "unknown schemaVersion");
        assertThrows(StreamContractException.class, () -> event(1, "1.00", ok), "total differs from lines");
        assertThrows(StreamContractException.class, () -> event(1, "18990.001", ok), "more than two decimals");
        assertThrows(StreamContractException.class, () -> event(1, "37980.00", List.of(item(P1, 1, "18990.00"), item(P1, 1, "18990.00"))), "duplicate product");
        assertThrows(StreamContractException.class, () -> item(P1, 0, "1.00"), "quantity below 1");
        assertThrows(StreamContractException.class, () -> item(P1, 1001, "1.00"), "quantity above 1000");
        assertThrows(StreamContractException.class, () -> new OrderRegisteredStreamV1.Item(P1, "x", 2, new BigDecimal("1.00"), new BigDecimal("3.00")), "lineTotal mismatch");
        assertThrows(StreamContractException.class, () -> new OrderRegisteredStreamV1(1, UUID.randomUUID(), UUID.randomUUID(), "tenant",
                Instant.now(), "clp", new BigDecimal("18990.00"), 1, ok), "currency must be ISO 4217 uppercase");
        assertThrows(StreamContractException.class, () -> new OrderRegisteredStreamV1(1, UUID.randomUUID(), UUID.randomUUID(), "tenant",
                Instant.now(), "CLP", new BigDecimal("18990.00"), 2, ok), "itemCount differs from items");
        assertThrows(StreamContractException.class, () -> new OrderRegisteredStreamV1(1, UUID.randomUUID(), UUID.randomUUID(), "x".repeat(101),
                Instant.now(), "CLP", new BigDecimal("18990.00"), 1, ok), "tenantId too long");
    }

    static ProductSalesMetricV1 metric(String key, long version) {
        var date = LocalDate.parse("2026-11-24");
        return new ProductSalesMetricV1(1, key, "tenant", P1, "Producto", date, "CLP", 3, 2,
                new BigDecimal("56970.00"), version, UUID.randomUUID(), Instant.now());
    }

    @Test void metricKeyAndVersionAreValidated() {
        String key = ProductSalesMetricV1.key("tenant", P1, LocalDate.parse("2026-11-24"), "CLP");
        assertEquals("tenant:" + P1 + ":2026-11-24:CLP", key);
        assertEquals(key, metric(key, 1).metricKey());
        assertThrows(StreamContractException.class, () -> metric("tenant:" + P1 + ":2026-11-25:CLP", 1), "metricKey mismatch");
        assertThrows(StreamContractException.class, () -> metric(key, 0), "version must be positive");
    }

    @Test void jsonHasNoJavaTypeHeadersAndDeserializesIntoFixedType() {
        var event = event(1, "30970.00", List.of(item(P1, 1, "18990.00"), item(P2, 2, "5990.00")));
        var headers = new RecordHeaders();
        try (var serializer = new JacksonJsonSerializer<Object>(); var deserializer = new JacksonJsonDeserializer<>(OrderRegisteredStreamV1.class, false)) {
            serializer.configure(java.util.Map.of(JacksonJsonSerializer.ADD_TYPE_INFO_HEADERS, false), false);
            byte[] bytes = serializer.serialize("t", headers, event);
            assertFalse(headers.iterator().hasNext(), "no __TypeId__ headers");
            String json = new String(bytes, java.nio.charset.StandardCharsets.UTF_8);
            assertTrue(json.startsWith("{\"schemaVersion\":1,\"eventId\":"), json);
            assertTrue(json.contains("\"occurredAt\":\"2026-11-24T14:05:12.345678Z\""), "ISO-8601 UTC timestamp: " + json);
            assertTrue(json.contains("\"total\":30970.00"), "two decimals preserved: " + json);
            assertEquals(event, deserializer.deserialize("t", headers, bytes));
            byte[] invalid = json.replace("\"schemaVersion\":1", "\"schemaVersion\":2").getBytes(java.nio.charset.StandardCharsets.UTF_8);
            var failure = assertThrows(RuntimeException.class, () -> deserializer.deserialize("t", headers, invalid));
            assertInstanceOf(StreamContractException.class, rootCause(failure), "contract violations surface as StreamContractException");
        }
    }

    static Throwable rootCause(Throwable error) {
        while (error.getCause() != null && error.getCause() != error) error = error.getCause();
        return error;
    }
}
