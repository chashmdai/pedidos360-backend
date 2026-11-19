package cl.duoc.pedidos360.sales.application;

import cl.duoc.pedidos360.sales.domain.DailyProductSales;
import java.util.List;

/** Publishes complete accumulator states; returns only after the broker confirms them, otherwise throws. */
public interface MetricPublisher { void publish(List<DailyProductSales> states); }
