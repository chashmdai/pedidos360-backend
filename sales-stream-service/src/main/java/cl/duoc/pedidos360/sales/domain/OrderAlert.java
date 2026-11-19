package cl.duoc.pedidos360.sales.domain;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Set;
import java.util.UUID;

/** An order that requires attention. Contains no personal identity. */
public record OrderAlert(UUID eventId, UUID orderId, String tenantId, Set<Reason> reasons, BigDecimal total,
                         String currency, int lineCount, Instant occurredAt, Instant detectedAt) {
    public enum Reason { HIGH_VALUE, MANY_LINES }

    public OrderAlert { reasons = Set.copyOf(reasons); }
}
