package cl.duoc.pedidos360.sales.infrastructure.streaming;

import cl.duoc.pedidos360.kafka.OrderRegisteredStreamV1;
import cl.duoc.pedidos360.kafka.ProductSalesMetricV1;
import cl.duoc.pedidos360.sales.domain.DailyProductSales;
import cl.duoc.pedidos360.sales.domain.RegisteredOrder;
import cl.duoc.pedidos360.sales.domain.SalesKey;

/** Explicit translation between the transport contracts and the analytics model. */
final class StreamMapping {
    private StreamMapping() {}

    static RegisteredOrder order(OrderRegisteredStreamV1 event) {
        var lines = event.items().stream().map(i -> new RegisteredOrder.Line(i.productId(), i.productName(), i.quantity(), i.lineTotal())).toList();
        return new RegisteredOrder(event.eventId(), event.orderId(), event.tenantId(), event.occurredAt(), event.currency(), event.total(), lines);
    }

    static ProductSalesMetricV1 metric(DailyProductSales s) {
        var k = s.key();
        return new ProductSalesMetricV1(1, k.metricKey(), k.tenantId(), k.productId(), s.productName(), k.businessDate(), k.currency(),
                s.unitsSold(), s.ordersCount(), s.revenue(), s.version(), s.lastEventId(), s.updatedAt());
    }

    static DailyProductSales state(ProductSalesMetricV1 m) {
        return new DailyProductSales(new SalesKey(m.tenantId(), m.productId(), m.businessDate(), m.currency()), m.productName(),
                m.unitsSold(), m.ordersCount(), m.revenue(), m.version(), m.lastEventId(), m.updatedAt());
    }
}
