package cl.duoc.pedidos360.sales;

import static cl.duoc.pedidos360.sales.Fixtures.*;
import static org.junit.jupiter.api.Assertions.*;

import cl.duoc.pedidos360.sales.application.LiveSalesView;
import cl.duoc.pedidos360.sales.domain.OrderAlert;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class LiveSalesViewTest {
    static final LocalDate TODAY = LocalDate.parse("2026-11-24");
    final LiveSalesView view = new LiveSalesView(50, CLOCK);

    @Test void keepsOnlyTheHighestVersionPerKey() {
        assertTrue(view.accept(state("t", P1, TODAY, 2, "200.00")));
        assertFalse(view.accept(state("t", P1, TODAY, 1, "100.00")), "older version arriving late is discarded");
        assertFalse(view.accept(state("t", P1, TODAY, 2, "999.00")), "equal version is not newer");
        assertTrue(view.accept(state("t", P1, TODAY, 3, "300.00")));
        var products = view.snapshot("t").products();
        assertEquals(1, products.size());
        assertEquals(3, products.getFirst().version());
        assertEquals(0, new BigDecimal("300.00").compareTo(products.getFirst().revenue()));
    }

    @Test void snapshotIsFilteredByTenantAndCurrentUtcDay() {
        view.accept(state("t", P1, TODAY, 1, "100.00"));
        view.accept(state("t", P2, TODAY.minusDays(1), 1, "100.00"));
        view.accept(state("other", P1, TODAY, 1, "500.00"));
        var snapshot = view.snapshot("t");
        assertEquals(TODAY, snapshot.businessDate());
        assertEquals(1, snapshot.products().size());
        assertEquals(P1, snapshot.products().getFirst().key().productId());
        assertEquals(NOW, snapshot.lastUpdate());
        assertTrue(view.snapshot("nobody").products().isEmpty());
        assertNull(view.snapshot("nobody").lastUpdate());
    }

    @Test void alertsAreBoundedNewestFirstDeduplicatedAndFilteredByTenant() {
        var small = new LiveSalesView(3, CLOCK);
        UUID last = null;
        for (int i = 0; i < 5; i++) {
            last = UUID.randomUUID();
            small.recordAlert(new OrderAlert(last, UUID.randomUUID(), "t", Set.of(OrderAlert.Reason.HIGH_VALUE), BigDecimal.TEN, "CLP", 1, NOW, NOW));
        }
        var repeated = new OrderAlert(last, UUID.randomUUID(), "t", Set.of(OrderAlert.Reason.HIGH_VALUE), BigDecimal.TEN, "CLP", 1, NOW, NOW);
        small.recordAlert(repeated);
        small.recordAlert(new OrderAlert(UUID.randomUUID(), UUID.randomUUID(), "other", Set.of(OrderAlert.Reason.MANY_LINES), BigDecimal.TEN, "CLP", 11, NOW, NOW));
        var alerts = small.snapshot("t").alerts();
        assertEquals(2, alerts.size(), "limit 3 shared across tenants; the other tenant's alert is hidden");
        assertEquals(last, alerts.getFirst().eventId(), "newest first, redelivery not duplicated");
    }
}
