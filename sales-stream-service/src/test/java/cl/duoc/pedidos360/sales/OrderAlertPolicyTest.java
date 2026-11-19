package cl.duoc.pedidos360.sales;

import static cl.duoc.pedidos360.sales.Fixtures.*;
import static org.junit.jupiter.api.Assertions.*;

import cl.duoc.pedidos360.sales.application.OrderAlertPolicy;
import cl.duoc.pedidos360.sales.domain.OrderAlert.Reason;
import cl.duoc.pedidos360.sales.domain.RegisteredOrder;
import java.math.BigDecimal;
import java.util.Set;
import java.util.UUID;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

class OrderAlertPolicyTest {
    final OrderAlertPolicy policy = new OrderAlertPolicy(new BigDecimal("50000"), "CLP", 10, CLOCK);

    static RegisteredOrder lines(int count) {
        return order("t", "CLP", NOW, IntStream.range(0, count).mapToObj(i -> line(UUID.randomUUID(), 1, "100.00")).toArray(RegisteredOrder.Line[]::new));
    }

    @Test void highValueStartsExactlyAtTheThresholdInClp() {
        assertEquals(Set.of(Reason.HIGH_VALUE), policy.evaluate(order("t", "CLP", NOW, line(P1, 1, "50000.00"))).orElseThrow().reasons());
        assertTrue(policy.evaluate(order("t", "CLP", NOW, line(P1, 1, "49999.99"))).isEmpty());
        assertTrue(policy.evaluate(order("t", "USD", NOW, line(P1, 1, "60000.00"))).isEmpty(), "other currencies are not comparable");
    }

    @Test void moreThanTenLinesIsALargeOrder() {
        assertTrue(policy.evaluate(lines(10)).isEmpty());
        var alert = policy.evaluate(lines(11)).orElseThrow();
        assertEquals(Set.of(Reason.MANY_LINES), alert.reasons());
        assertEquals(11, alert.lineCount());
        assertEquals(NOW, alert.detectedAt());
    }
}
