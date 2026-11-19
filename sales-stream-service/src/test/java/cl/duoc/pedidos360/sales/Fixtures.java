package cl.duoc.pedidos360.sales;

import cl.duoc.pedidos360.sales.domain.*;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;

final class Fixtures {
    static final Instant NOW = Instant.parse("2026-11-24T14:05:13Z");
    static final Clock CLOCK = Clock.fixed(NOW, ZoneOffset.UTC);
    static final UUID P1 = UUID.fromString("10000000-0000-0000-0000-000000000001");
    static final UUID P2 = UUID.fromString("10000000-0000-0000-0000-000000000002");

    static RegisteredOrder order(String tenant, String currency, Instant at, RegisteredOrder.Line... lines) {
        var total = Arrays.stream(lines).map(RegisteredOrder.Line::lineTotal).reduce(BigDecimal.ZERO, BigDecimal::add);
        return new RegisteredOrder(UUID.randomUUID(), UUID.randomUUID(), tenant, at, currency, total, List.of(lines));
    }

    static RegisteredOrder.Line line(UUID product, int quantity, String unitPrice) {
        return new RegisteredOrder.Line(product, "Producto " + product.toString().substring(35), quantity,
                new BigDecimal(unitPrice).multiply(BigDecimal.valueOf(quantity)));
    }

    static DailyProductSales state(String tenant, UUID product, LocalDate day, long version, String revenue) {
        return new DailyProductSales(new SalesKey(tenant, product, day, "CLP"), "Producto", version, version, new BigDecimal(revenue),
                version, UUID.randomUUID(), NOW);
    }
}
