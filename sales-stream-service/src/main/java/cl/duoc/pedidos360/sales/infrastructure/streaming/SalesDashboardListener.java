package cl.duoc.pedidos360.sales.infrastructure.streaming;

import cl.duoc.pedidos360.kafka.ProductSalesMetricV1;
import cl.duoc.pedidos360.sales.application.LiveSalesView;
import java.util.Map;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.TopicPartition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.listener.ConsumerSeekAware;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

/**
 * Group pedidos360-sales-dashboard: seeks to the beginning of the compacted metrics topic on every
 * assignment, rebuilding the last state of each metric in memory (highest version wins).
 */
@Component
public class SalesDashboardListener implements ConsumerSeekAware {
    private static final Logger log = LoggerFactory.getLogger(SalesDashboardListener.class);
    private final LiveSalesView view;
    private final String group;
    private final ConsumptionLog consumption;

    public SalesDashboardListener(LiveSalesView view, @Value("${pedidos.kafka.groups.sales-dashboard}") String group) {
        this.view = view; this.group = group; this.consumption = new ConsumptionLog(group);
    }

    @Override public void onPartitionsAssigned(Map<TopicPartition, Long> assignments, ConsumerSeekCallback callback) {
        callback.seekToBeginning(assignments.keySet());
        log.info("DASHBOARD_REBUILD group={} partitions={} from=beginning", group, assignments.keySet());
    }

    @KafkaListener(id = "sales-dashboard", groupId = "${pedidos.kafka.groups.sales-dashboard}", clientIdPrefix = "sales-dashboard",
            topics = "${pedidos.kafka.topics.product-metrics}", containerFactory = StreamingConfiguration.DASHBOARD_FACTORY)
    void materialize(ConsumerRecord<String, ProductSalesMetricV1> record, @Header(KafkaHeaders.DELIVERY_ATTEMPT) int attempt) {
        boolean applied = view.accept(StreamMapping.state(record.value()));
        consumption.ok(record, attempt, applied ? "VIEW_UPDATED version=" + record.value().version()
                : "STALE_VERSION_DISCARDED version=" + record.value().version());
    }
}
