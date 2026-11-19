package cl.duoc.pedidos360.sales.application;

import cl.duoc.pedidos360.sales.domain.DailyProductSales;
import cl.duoc.pedidos360.sales.domain.RegisteredOrder;
import cl.duoc.pedidos360.sales.domain.SalesKey;
import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.Optional;

/** Persistence port for the accumulators (pedidos360_streams). */
public interface SalesLedger {
    /**
     * In ONE transaction: records eventId as processed and atomically adds the order lines to their
     * accumulators. Returns the resulting states, or empty if eventId was already processed (nothing changes).
     */
    Optional<List<DailyProductSales>> applyOnce(RegisteredOrder order, String consumerGroup, Instant now);

    /** Current committed states of the given accumulators. */
    List<DailyProductSales> current(Collection<SalesKey> keys);
}
