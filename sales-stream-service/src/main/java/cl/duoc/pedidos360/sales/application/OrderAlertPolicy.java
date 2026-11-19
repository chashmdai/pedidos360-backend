package cl.duoc.pedidos360.sales.application;

import cl.duoc.pedidos360.sales.domain.OrderAlert;
import cl.duoc.pedidos360.sales.domain.OrderAlert.Reason;
import cl.duoc.pedidos360.sales.domain.RegisteredOrder;
import java.math.BigDecimal;
import java.time.Clock;
import java.util.EnumSet;
import java.util.Objects;
import java.util.Optional;

/**
 * High-value rule: total &ge; threshold in the configured currency (50.000 CLP in the lab;
 * amounts in other currencies are not comparable). Large-order rule: more than maxLines lines.
 */
public class OrderAlertPolicy {
    private final BigDecimal highValue;
    private final String highValueCurrency;
    private final int maxLines;
    private final Clock clock;

    public OrderAlertPolicy(BigDecimal highValue, String highValueCurrency, int maxLines, Clock clock) {
        this.highValue = Objects.requireNonNull(highValue); this.highValueCurrency = Objects.requireNonNull(highValueCurrency);
        this.maxLines = maxLines; this.clock = clock;
    }

    public Optional<OrderAlert> evaluate(RegisteredOrder order) {
        var reasons = EnumSet.noneOf(Reason.class);
        if (highValueCurrency.equals(order.currency()) && order.total().compareTo(highValue) >= 0) reasons.add(Reason.HIGH_VALUE);
        if (order.lines().size() > maxLines) reasons.add(Reason.MANY_LINES);
        if (reasons.isEmpty()) return Optional.empty();
        return Optional.of(new OrderAlert(order.eventId(), order.orderId(), order.tenantId(), reasons, order.total(),
                order.currency(), order.lines().size(), order.occurredAt(), clock.instant()));
    }
}
