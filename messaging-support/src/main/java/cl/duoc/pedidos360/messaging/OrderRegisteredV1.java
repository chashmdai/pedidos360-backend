package cl.duoc.pedidos360.messaging;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

/** Transport contract only. Never exports an Order aggregate or JPA entity. */
public record OrderRegisteredV1(int schemaVersion, UUID eventId, UUID orderId, String tenantId,
                                Instant occurredAt, BigDecimal total, String currency, int itemCount) {
    public OrderRegisteredV1 {
        if (schemaVersion != 1 || eventId == null || orderId == null || occurredAt == null
                || tenantId == null || tenantId.isBlank() || tenantId.length() > 100
                || total == null || total.signum() < 0 || total.precision() > 19 || total.scale() > 2
                || currency == null || !currency.matches("[A-Z]{3}") || itemCount < 1 || itemCount > 50) {
            throw new IllegalArgumentException("Invalid OrderRegisteredV1 contract");
        }
    }
}
