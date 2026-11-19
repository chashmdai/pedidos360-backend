package cl.duoc.pedidos360.sales.application;

import cl.duoc.pedidos360.sales.domain.DailyProductSales;
import cl.duoc.pedidos360.sales.domain.RegisteredOrder;
import java.time.Clock;
import java.util.List;

/**
 * Per-product daily aggregation with idempotency by eventId. The accumulators are committed first and
 * the resulting states are published afterwards. If publishing fails the event is retried: the duplicate
 * check prevents counting it twice, and the current (complete) states are published again.
 */
public class SalesAggregationService {
    public record Outcome(boolean duplicate, List<DailyProductSales> published) {}

    private final SalesLedger ledger;
    private final MetricPublisher publisher;
    private final Clock clock;

    public SalesAggregationService(SalesLedger ledger, MetricPublisher publisher, Clock clock) {
        this.ledger = ledger; this.publisher = publisher; this.clock = clock;
    }

    public Outcome aggregate(RegisteredOrder order, String consumerGroup) {
        var applied = ledger.applyOnce(order, consumerGroup, clock.instant());
        var states = applied.orElseGet(() -> ledger.current(order.keys()));
        publisher.publish(states);
        return new Outcome(applied.isEmpty(), states);
    }
}
