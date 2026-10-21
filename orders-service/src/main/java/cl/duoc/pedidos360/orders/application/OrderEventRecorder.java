package cl.duoc.pedidos360.orders.application;
import cl.duoc.pedidos360.orders.domain.Order;
/** Called inside the persistence transaction; implementations must not contact a broker here. */
public interface OrderEventRecorder { void record(Order order); }
