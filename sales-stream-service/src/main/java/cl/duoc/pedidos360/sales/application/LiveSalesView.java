package cl.duoc.pedidos360.sales.application;

import cl.duoc.pedidos360.sales.domain.DailyProductSales;
import cl.duoc.pedidos360.sales.domain.OrderAlert;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * In-memory materialized view: per metric key the state with the highest version (older or equal
 * versions are discarded), plus the most recent alerts (bounded). Rebuilt from the compacted topic.
 */
public class LiveSalesView {
    public record Snapshot(LocalDate businessDate, Instant generatedAt, Instant lastUpdate,
                           List<DailyProductSales> products, List<OrderAlert> alerts) {}

    private final Map<String, DailyProductSales> metrics = new ConcurrentHashMap<>();
    private final Deque<OrderAlert> alerts = new ArrayDeque<>();
    private final int alertLimit;
    private final Clock clock;

    public LiveSalesView(int alertLimit, Clock clock) { this.alertLimit = alertLimit; this.clock = clock; }

    /** Returns true if the state was applied, false if it was not newer than the known one. */
    public boolean accept(DailyProductSales state) {
        var applied = new boolean[1];
        metrics.compute(state.key().metricKey(), (key, known) -> {
            if (!state.newerThan(known)) return known;
            applied[0] = true;
            return state;
        });
        return applied[0];
    }

    public synchronized void recordAlert(OrderAlert alert) {
        if (alerts.stream().anyMatch(a -> a.eventId().equals(alert.eventId()))) return; // redelivered event
        alerts.addFirst(alert);
        while (alerts.size() > alertLimit) alerts.removeLast();
    }

    /** Current UTC day only, filtered by the tenant of the validated token. */
    public Snapshot snapshot(String tenantId) {
        var now = clock.instant();
        var today = LocalDate.ofInstant(now, ZoneOffset.UTC);
        var products = metrics.values().stream()
                .filter(m -> m.key().tenantId().equals(tenantId) && m.key().businessDate().equals(today))
                .sorted(Comparator.comparing(DailyProductSales::revenue).reversed().thenComparing(DailyProductSales::productName))
                .toList();
        List<OrderAlert> recent;
        synchronized (this) { recent = alerts.stream().filter(a -> a.tenantId().equals(tenantId)).toList(); }
        var lastUpdate = products.stream().map(DailyProductSales::updatedAt).max(Comparator.naturalOrder()).orElse(null);
        return new Snapshot(today, now, lastUpdate, products, recent);
    }

    /** Forgets the materialized metrics (used before a full rebuild from the compacted topic). */
    public void clearMetrics() { metrics.clear(); }
}
