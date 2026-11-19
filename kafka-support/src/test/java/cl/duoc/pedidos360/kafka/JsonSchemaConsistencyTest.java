package cl.duoc.pedidos360.kafka;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** The published JSON Schemas list exactly the fields of the Java records, and their examples are valid. */
class JsonSchemaConsistencyTest {
    static final JsonMapper JSON = new JsonMapper();

    static JsonNode schema(String file) { return JSON.readTree(Path.of("..", "contracts", file).toFile()); }

    static Set<String> fields(Class<? extends Record> type) {
        return new TreeSet<>(Arrays.stream(type.getRecordComponents()).map(c -> c.getName()).toList());
    }

    static Set<String> names(JsonNode array) {
        var result = new TreeSet<String>();
        array.forEach(n -> result.add(n.asString()));
        return result;
    }

    @Test void orderSchemaMatchesRecordAndExampleIsValid() {
        var schema = schema("order-registered-stream-v1.schema.json");
        assertEquals(fields(OrderRegisteredStreamV1.class), names(schema.get("required")));
        assertEquals(fields(OrderRegisteredStreamV1.class), new TreeSet<>(schema.get("properties").propertyNames()));
        var items = schema.get("properties").get("items").get("items");
        assertEquals(fields(OrderRegisteredStreamV1.Item.class), names(items.get("required")));
        var example = JSON.treeToValue(schema.get("examples").get(0), OrderRegisteredStreamV1.class);
        assertEquals(2, example.items().size());
    }

    @Test void metricSchemaMatchesRecordAndExampleIsValid() {
        var schema = schema("product-sales-metric-v1.schema.json");
        assertEquals(fields(ProductSalesMetricV1.class), names(schema.get("required")));
        assertEquals(fields(ProductSalesMetricV1.class), new TreeSet<>(schema.get("properties").propertyNames()));
        var example = JSON.treeToValue(schema.get("examples").get(0), ProductSalesMetricV1.class);
        assertEquals(List.of(2L), List.of(example.version()));
    }
}
