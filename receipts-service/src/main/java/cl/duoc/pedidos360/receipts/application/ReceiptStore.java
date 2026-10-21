package cl.duoc.pedidos360.receipts.application;
import cl.duoc.pedidos360.messaging.OrderRegisteredV1;
import java.io.IOException;
import java.util.List;
public interface ReceiptStore {
    /** Returns false for an identical duplicate. Conflicting reuse of an event ID is invalid. */
    boolean saveOnce(OrderRegisteredV1 event) throws IOException;
    List<OrderRegisteredV1> findByTenant(String tenant) throws IOException;
}
