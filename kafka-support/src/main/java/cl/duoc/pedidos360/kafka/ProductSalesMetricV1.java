package cl.duoc.pedidos360.kafka;

import static cl.duoc.pedidos360.kafka.Contracts.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

/**
 * Complete state (not an increment) of a daily per-product accumulator (report table 9;
 * contracts/product-sales-metric-v1.schema.json). Message key and metricKey:
 * tenantId:productId:businessDate:currency. Republishing the same state is harmless; a
 * consumer keeps the highest version per key.
 */
public record ProductSalesMetricV1(int schemaVersion, String metricKey, String tenantId, UUID productId,
                                   String productName, LocalDate businessDate, String currency,
                                   long unitsSold, long ordersCount, BigDecimal revenue, long version,
                                   UUID lastEventId, Instant updatedAt) {
    private static final String NAME = "ProductSalesMetricV1";

    public static String key(String tenantId, UUID productId, LocalDate businessDate, String currency) {
        return tenantId + ":" + productId + ":" + businessDate + ":" + currency;
    }

    public ProductSalesMetricV1 {
        require(schemaVersion == 1, NAME, "unsupported schemaVersion");
        require(text(tenantId, 100), NAME, "tenantId must have 1-100 characters");
        require(productId != null && businessDate != null && lastEventId != null && updatedAt != null, NAME,
                "productId, businessDate, lastEventId and updatedAt are required");
        require(text(productName, 120), NAME, "productName must have 1-120 characters");
        require(isoCurrency(currency), NAME, "currency must be an ISO 4217 code");
        require(key(tenantId, productId, businessDate, currency).equals(metricKey), NAME,
                "metricKey must be tenantId:productId:businessDate:currency");
        require(unitsSold >= 0 && ordersCount >= 0, NAME, "unitsSold and ordersCount must be non-negative");
        require(amount(revenue), NAME, "revenue must be non-negative with two decimals");
        require(version >= 1, NAME, "version must be positive");
    }
}
