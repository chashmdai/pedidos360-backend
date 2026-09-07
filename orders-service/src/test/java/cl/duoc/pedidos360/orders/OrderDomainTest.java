package cl.duoc.pedidos360.orders;
import cl.duoc.pedidos360.orders.domain.*;
import cl.duoc.pedidos360.orders.application.*;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
class OrderDomainTest {
    private final OwnerId owner=new OwnerId("tenant","alice");
    @Test void multitemOrderUsesDecimalSnapshotsAndImmutableLines() {
        var lines=new ArrayList<>(List.of(new OrderItem(UUID.randomUUID(),"A",new Money(new BigDecimal("0.10"),"CLP"),3),
            new OrderItem(UUID.randomUUID(),"B",new Money(new BigDecimal("0.20"),"CLP"),1)));
        var order=new Order(UUID.randomUUID(),owner,lines,Instant.EPOCH,Order.Status.REGISTERED);
        lines.clear();
        assertEquals(new BigDecimal("0.50"),order.total().amount()); assertEquals(2,order.items().size());
        assertThrows(UnsupportedOperationException.class,()->order.items().clear());
    }
    @Test void invalidQuantityCurrencyAndEmptyOrdersAreRejected() {
        assertThrows(IllegalArgumentException.class,()->new OrderItem(UUID.randomUUID(),"A",new Money(BigDecimal.ONE,"CLP"),0));
        assertThrows(IllegalArgumentException.class,()->new Money(BigDecimal.ONE,"CLP").add(new Money(BigDecimal.ONE,"USD")));
        assertThrows(IllegalArgumentException.class,()->new Order(UUID.randomUUID(),owner,List.of(),Instant.EPOCH,Order.Status.REGISTERED));
    }
    @Test void lookupFailureDoesNotPersistPartialOrder() {
        var repository=mock(OrderRepository.class);
        var products=mock(ProductLookup.class);
        var id=UUID.randomUUID();
        when(products.get(id)).thenThrow(new NoSuchElementException());
        var service=new OrderService(repository,products,Clock.systemUTC());
        assertThrows(NoSuchElementException.class,()->service.create(owner,List.of(new OrderService.RequestedItem(id,1))));
        verifyNoInteractions(repository);
    }
}
