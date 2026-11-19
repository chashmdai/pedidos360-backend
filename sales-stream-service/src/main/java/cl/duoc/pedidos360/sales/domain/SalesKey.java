package cl.duoc.pedidos360.sales.domain;

import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;

/** Identity of a daily accumulator: tenant, product, UTC business day and currency. */
public record SalesKey(String tenantId, UUID productId, LocalDate businessDate, String currency) implements Comparable<SalesKey> {
    public SalesKey {
        Objects.requireNonNull(tenantId); Objects.requireNonNull(productId);
        Objects.requireNonNull(businessDate); Objects.requireNonNull(currency);
    }

    /** Same format as the Kafka message key and ProductSalesMetricV1.metricKey. */
    public String metricKey() { return tenantId + ":" + productId + ":" + businessDate + ":" + currency; }

    @Override public int compareTo(SalesKey other) { return metricKey().compareTo(other.metricKey()); }
}
