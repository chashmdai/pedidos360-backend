package cl.duoc.pedidos360.sales.configuration;

import cl.duoc.pedidos360.sales.application.*;
import java.math.BigDecimal;
import java.time.Clock;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Wires the framework-free use cases. */
@Configuration
public class SalesStreamConfiguration {
    @Bean Clock clock() { return Clock.systemUTC(); }

    @Bean SalesAggregationService salesAggregationService(SalesLedger ledger, MetricPublisher publisher, Clock clock) {
        return new SalesAggregationService(ledger, publisher, clock);
    }

    @Bean OrderAlertPolicy orderAlertPolicy(@Value("${pedidos.streams.alerts.high-value}") BigDecimal highValue,
                                            @Value("${pedidos.streams.alerts.high-value-currency}") String currency,
                                            @Value("${pedidos.streams.alerts.max-lines}") int maxLines, Clock clock) {
        return new OrderAlertPolicy(highValue, currency, maxLines, clock);
    }

    @Bean LiveSalesView liveSalesView(@Value("${pedidos.streams.alerts.recent-limit}") int limit, Clock clock) {
        return new LiveSalesView(limit, clock);
    }
}
