package cl.duoc.pedidos360.sales.domain;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

/** A registered order as seen by analytics; translated from the streaming contract by infrastructure. */
public record RegisteredOrder(UUID eventId, UUID orderId, String tenantId, Instant occurredAt, String currency,
                              BigDecimal total, List<Line> lines) {
    public record Line(UUID productId, String productName, int quantity, BigDecimal lineTotal) {}

    public RegisteredOrder {
        Objects.requireNonNull(eventId); Objects.requireNonNull(orderId); Objects.requireNonNull(tenantId);
        Objects.requireNonNull(occurredAt); Objects.requireNonNull(currency); Objects.requireNonNull(total);
        lines = List.copyOf(lines);
    }

    /** The UTC calendar day of the order determines its daily accumulator. */
    public LocalDate businessDate() { return LocalDate.ofInstant(occurredAt, ZoneOffset.UTC); }

    public SalesKey keyOf(Line line) { return new SalesKey(tenantId, line.productId(), businessDate(), currency); }

    public List<SalesKey> keys() { return lines.stream().map(this::keyOf).sorted().toList(); }
}
