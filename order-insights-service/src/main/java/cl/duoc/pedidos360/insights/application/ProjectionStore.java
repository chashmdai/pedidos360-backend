package cl.duoc.pedidos360.insights.application;
import cl.duoc.pedidos360.messaging.OrderRegisteredV1;
import java.io.IOException;
import java.util.List;
public interface ProjectionStore {
    boolean saveOnce(OrderRegisteredV1 event) throws IOException;
    List<OrderRegisteredV1> findByTenant(String tenant) throws IOException;
}
