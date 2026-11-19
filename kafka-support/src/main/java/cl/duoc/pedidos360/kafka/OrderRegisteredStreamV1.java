package cl.duoc.pedidos360.kafka;

import static cl.duoc.pedidos360.kafka.Contracts.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.HashSet;
import java.util.List;
import java.util.UUID;

/**
 * Streaming contract of a registered order (report table 8; contracts/order-registered-stream-v1.schema.json).
 * Message key: orderId. Carries the order lines so analytics need neither Catalog nor Orders.
 * Deliberately excludes the user's oid, name, e-mail and tokens.
 */
public record OrderRegisteredStreamV1(int schemaVersion, UUID eventId, UUID orderId, String tenantId,
                                      Instant occurredAt, String currency, BigDecimal total, int itemCount,
                                      List<Item> items) {
    private static final String NAME = "OrderRegisteredStreamV1";

    public record Item(UUID productId, String productName, int quantity, BigDecimal unitPrice, BigDecimal lineTotal) {
        public Item {
            require(productId != null, NAME, "items[].productId is required");
            require(text(productName, 120), NAME, "items[].productName must have 1-120 characters");
            require(quantity >= 1 && quantity <= 1000, NAME, "items[].quantity must be 1-1000");
            require(amount(unitPrice) && amount(lineTotal), NAME, "items[] amounts must be non-negative with two decimals");
            require(unitPrice.multiply(BigDecimal.valueOf(quantity)).compareTo(lineTotal) == 0, NAME,
                    "items[].lineTotal must equal unitPrice * quantity");
            unitPrice = money(unitPrice);
            lineTotal = money(lineTotal);
        }
    }

    public OrderRegisteredStreamV1 {
        require(schemaVersion == 1, NAME, "unsupported schemaVersion");
        require(eventId != null && orderId != null && occurredAt != null, NAME, "eventId, orderId and occurredAt are required");
        require(text(tenantId, 100), NAME, "tenantId must have 1-100 characters");
        require(isoCurrency(currency), NAME, "currency must be an ISO 4217 code");
        require(amount(total), NAME, "total must be non-negative with two decimals");
        require(itemCount >= 1 && itemCount <= 50, NAME, "itemCount must be 1-50");
        require(items != null && items.size() == itemCount && items.stream().allMatch(java.util.Objects::nonNull), NAME, "items must contain itemCount lines");
        items = List.copyOf(items);
        require(new HashSet<>(items.stream().map(Item::productId).toList()).size() == items.size(), NAME, "products must be unique");
        require(items.stream().map(Item::lineTotal).reduce(BigDecimal.ZERO, BigDecimal::add).compareTo(total) == 0, NAME,
                "total must equal the sum of lineTotal");
        total = money(total);
    }
}
