package cl.duoc.pedidos360.sales.infrastructure.streaming;

import cl.duoc.pedidos360.kafka.OrderRegisteredStreamV1;
import cl.duoc.pedidos360.sales.application.LiveSalesView;
import cl.duoc.pedidos360.sales.application.OrderAlertPolicy;
import cl.duoc.pedidos360.sales.application.SalesAggregationService;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

/**
 * Two independent groups on pedidos360.orders.registered.v1. Listeners only receive the DTO, log the
 * record context and delegate to the use cases; no business logic here.
 */
@Component
public class OrderEventListeners {
    private static final Logger log = LoggerFactory.getLogger(OrderEventListeners.class);
    private final SalesAggregationService aggregation;
    private final OrderAlertPolicy alerts;
    private final LiveSalesView view;
    private final String aggregatorGroup;
    private final ConsumptionLog aggregatorLog;
    private final ConsumptionLog monitorLog;

    public OrderEventListeners(SalesAggregationService aggregation, OrderAlertPolicy alerts, LiveSalesView view,
                               @Value("${pedidos.kafka.groups.sales-aggregator}") String aggregatorGroup,
                               @Value("${pedidos.kafka.groups.order-monitor}") String monitorGroup) {
        this.aggregation = aggregation; this.alerts = alerts; this.view = view; this.aggregatorGroup = aggregatorGroup;
        this.aggregatorLog = new ConsumptionLog(aggregatorGroup); this.monitorLog = new ConsumptionLog(monitorGroup);
    }

    @KafkaListener(id = "sales-aggregator", groupId = "${pedidos.kafka.groups.sales-aggregator}", clientIdPrefix = "sales-aggregator",
            topics = "${pedidos.kafka.topics.orders-registered}", containerFactory = StreamingConfiguration.AGGREGATOR_FACTORY)
    void aggregate(ConsumerRecord<String, OrderRegisteredStreamV1> record, @Header(KafkaHeaders.DELIVERY_ATTEMPT) int attempt) {
        var outcome = aggregation.aggregate(StreamMapping.order(record.value()), aggregatorGroup);
        if (!outcome.duplicate()) aggregatorLog.ok(record, attempt, "ACCUMULATORS_UPDATED metrics=" + outcome.published().size());
        // A retry of this same delivery after a post-commit publication failure: recovery, not a duplicate.
        else if (attempt > 1) aggregatorLog.ok(record, attempt, "METRICS_REPUBLISHED metrics=" + outcome.published().size());
        else aggregatorLog.duplicate(record, attempt);
    }

    @KafkaListener(id = "order-monitor", groupId = "${pedidos.kafka.groups.order-monitor}", clientIdPrefix = "order-monitor",
            topics = "${pedidos.kafka.topics.orders-registered}", containerFactory = StreamingConfiguration.MONITOR_FACTORY)
    void monitor(ConsumerRecord<String, OrderRegisteredStreamV1> record, @Header(KafkaHeaders.DELIVERY_ATTEMPT) int attempt) {
        var alert = alerts.evaluate(StreamMapping.order(record.value()));
        alert.ifPresent(a -> {
            view.recordAlert(a);
            log.warn("ORDER_ALERT eventId={} orderId={} reasons={} total={} currency={} lines={}",
                    a.eventId(), a.orderId(), a.reasons(), a.total().toPlainString(), a.currency(), a.lineCount());
        });
        monitorLog.ok(record, attempt, alert.isPresent() ? "ALERT" : "NO_ALERT");
    }
}
