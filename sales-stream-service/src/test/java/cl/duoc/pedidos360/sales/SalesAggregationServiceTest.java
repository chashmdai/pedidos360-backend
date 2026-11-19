package cl.duoc.pedidos360.sales;

import static cl.duoc.pedidos360.sales.Fixtures.*;
import static org.junit.jupiter.api.Assertions.*;

import cl.duoc.pedidos360.sales.application.*;
import cl.duoc.pedidos360.sales.domain.*;
import java.time.Instant;
import java.time.LocalDate;
import java.util.*;
import org.junit.jupiter.api.Test;

class SalesAggregationServiceTest {
    static class MemoryLedger implements SalesLedger {
        final Set<UUID> processed = new HashSet<>();
        final Map<SalesKey, DailyProductSales> rows = new TreeMap<>();
        public Optional<List<DailyProductSales>> applyOnce(RegisteredOrder order, String group, Instant now) {
            if (!processed.add(order.eventId())) return Optional.empty();
            for (var line : order.lines()) {
                var key = order.keyOf(line);
                var old = rows.get(key);
                rows.put(key, new DailyProductSales(key, line.productName(), (old == null ? 0 : old.unitsSold()) + line.quantity(),
                        (old == null ? 0 : old.ordersCount()) + 1, (old == null ? java.math.BigDecimal.ZERO : old.revenue()).add(line.lineTotal()),
                        (old == null ? 0 : old.version()) + 1, order.eventId(), now));
            }
            return Optional.of(current(order.keys()));
        }
        public List<DailyProductSales> current(Collection<SalesKey> keys) { return keys.stream().map(rows::get).filter(Objects::nonNull).toList(); }
    }

    final MemoryLedger ledger = new MemoryLedger();
    final List<List<DailyProductSales>> published = new ArrayList<>();
    int failures;
    final SalesAggregationService service = new SalesAggregationService(ledger, states -> {
        if (failures-- > 0) throw new IllegalStateException("broker unavailable");
        published.add(states);
    }, CLOCK);

    @Test void appliesOncePerEventIdAndPublishesCompleteStates() {
        var order = order("t", "CLP", NOW, line(P1, 2, "100.00"), line(P2, 1, "50.00"));
        var first = service.aggregate(order, "g");
        assertFalse(first.duplicate());
        assertEquals(2, first.published().size());
        var p1 = first.published().stream().filter(s -> s.key().productId().equals(P1)).findFirst().orElseThrow();
        assertEquals(2, p1.unitsSold()); assertEquals(1, p1.ordersCount()); assertEquals(0, new java.math.BigDecimal("200.00").compareTo(p1.revenue()));
        assertEquals(1, p1.version());
        assertEquals(LocalDate.parse("2026-11-24"), p1.key().businessDate());

        var again = service.aggregate(order, "g");
        assertTrue(again.duplicate(), "same eventId is a duplicate");
        assertEquals(first.published(), again.published(), "accumulators unchanged; the same complete states are republished");
    }

    @Test void publicationFailureAfterCommitIsRetriedWithoutDoubleCounting() {
        var order = order("t", "CLP", NOW, line(P1, 3, "10.00"));
        failures = 1;
        assertThrows(IllegalStateException.class, () -> service.aggregate(order, "g"), "propagates so the event is retried");
        var retry = service.aggregate(order, "g");
        assertTrue(retry.duplicate());
        assertEquals(3, retry.published().getFirst().unitsSold(), "counted once");
        assertEquals(1, retry.published().getFirst().version());
        assertEquals(1, published.size());
    }

    @Test void businessDateIsTheUtcDayOfTheOrder() {
        // 23:30 in Santiago (UTC-3) is already the next day in UTC.
        var late = order("t", "CLP", Instant.parse("2026-11-24T23:30:00-03:00"), line(P1, 1, "1.00"));
        assertEquals(LocalDate.parse("2026-11-25"), late.businessDate());
    }
}
