package cl.duoc.pedidos360.sales.infrastructure.persistence;

import cl.duoc.pedidos360.sales.application.SalesLedger;
import cl.duoc.pedidos360.sales.domain.DailyProductSales;
import cl.duoc.pedidos360.sales.domain.RegisteredOrder;
import cl.duoc.pedidos360.sales.domain.SalesKey;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class JdbcSalesLedger implements SalesLedger {
    // Atomic insert-or-add: concurrent consumers updating the same accumulator never lose increments.
    private static final String UPSERT = "INSERT INTO product_sales_daily(tenant_id,product_id,business_date,currency,product_name,"
            + "units_sold,orders_count,revenue,version,last_event_id,updated_at) VALUES (?,?,?,?,?,?,1,?,1,?,?) AS n "
            + "ON DUPLICATE KEY UPDATE product_name=n.product_name, units_sold=product_sales_daily.units_sold+n.units_sold, "
            + "orders_count=product_sales_daily.orders_count+1, revenue=product_sales_daily.revenue+n.revenue, "
            + "version=product_sales_daily.version+1, last_event_id=n.last_event_id, updated_at=n.updated_at";
    private static final String SELECT = "SELECT tenant_id,product_id,business_date,currency,product_name,units_sold,orders_count,"
            + "revenue,version,last_event_id,updated_at FROM product_sales_daily WHERE tenant_id=? AND product_id=? AND business_date=? AND currency=?";

    private final JdbcTemplate jdbc;

    public JdbcSalesLedger(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    @Override
    @Transactional(isolation = Isolation.READ_COMMITTED)
    public Optional<List<DailyProductSales>> applyOnce(RegisteredOrder order, String consumerGroup, Instant now) {
        int inserted = jdbc.update("INSERT IGNORE INTO processed_stream_event(event_id,order_id,consumer_group) VALUES (?,?,?)",
                order.eventId().toString(), order.orderId().toString(), consumerGroup);
        if (inserted == 0) return Optional.empty();   // already processed: accumulators stay unchanged
        // Stable key order keeps row-lock acquisition consistent across the three consumers.
        var lines = order.lines().stream().sorted(Comparator.comparing(order::keyOf)).toList();
        for (var line : lines) {
            var key = order.keyOf(line);
            jdbc.update(UPSERT, key.tenantId(), key.productId().toString(), key.businessDate(), key.currency(),
                    line.productName(), line.quantity(), line.lineTotal(), order.eventId().toString(), Timestamp.from(now));
        }
        return Optional.of(read(order.keys()));
    }

    @Override
    @Transactional(readOnly = true, isolation = Isolation.READ_COMMITTED)
    public List<DailyProductSales> current(Collection<SalesKey> keys) { return read(keys); }

    private List<DailyProductSales> read(Collection<SalesKey> keys) {
        var result = new ArrayList<DailyProductSales>(keys.size());
        for (var key : new TreeSet<>(keys)) {
            jdbc.query(SELECT, rs -> {
                result.add(new DailyProductSales(new SalesKey(rs.getString(1), UUID.fromString(rs.getString(2)), rs.getObject(3, java.time.LocalDate.class), rs.getString(4)),
                        rs.getString(5), rs.getLong(6), rs.getLong(7), rs.getBigDecimal(8), rs.getLong(9),
                        UUID.fromString(rs.getString(10)), rs.getTimestamp(11).toInstant()));
            }, key.tenantId(), key.productId().toString(), key.businessDate(), key.currency());
        }
        return result;
    }
}
