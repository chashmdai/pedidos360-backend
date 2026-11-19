package cl.duoc.pedidos360.sales.domain;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

/** Complete state of a daily accumulator (requested amounts, not payments). */
public record DailyProductSales(SalesKey key, String productName, long unitsSold, long ordersCount, BigDecimal revenue,
                                long version, UUID lastEventId, Instant updatedAt) {
    public DailyProductSales {
        Objects.requireNonNull(key); Objects.requireNonNull(productName); Objects.requireNonNull(revenue);
        Objects.requireNonNull(lastEventId); Objects.requireNonNull(updatedAt);
        if (version < 1 || unitsSold < 0 || ordersCount < 0 || revenue.signum() < 0) throw new IllegalArgumentException("Invalid accumulator state");
    }

    /** True when this state supersedes the other one for the same key (strictly higher version). */
    public boolean newerThan(DailyProductSales other) { return other == null || version > other.version; }
}
