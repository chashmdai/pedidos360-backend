package cl.duoc.pedidos360.receipts;
import cl.duoc.pedidos360.messaging.OrderRegisteredV1;
import cl.duoc.pedidos360.receipts.application.ReceiptStore;
import cl.duoc.pedidos360.receipts.infrastructure.*;
import com.rabbitmq.client.Channel;
import java.io.IOException;
import java.math.BigDecimal;
import java.nio.file.*;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import org.springframework.amqp.core.*;
import tools.jackson.databind.json.JsonMapper;

class ReceiptListenerTest {
    @TempDir Path directory;
    final JsonMapper json=new JsonMapper();
    OrderRegisteredV1 event() { return new OrderRegisteredV1(1,UUID.randomUUID(),UUID.randomUUID(),"tenant",Instant.now(),new BigDecimal("12.00"),"CLP",1); }
    Message message(OrderRegisteredV1 event) {
        var p=new MessageProperties();p.setMessageId(event.eventId().toString());p.setDeliveryTag(7);
        return new Message(json.writeValueAsBytes(event),p);
    }
    @Test void confirmsOnlyAfterDurableEffectAndAcknowledgesIdenticalDuplicate() throws Exception {
        var store=new FileReceiptStore(directory.toString(),json);var listener=new ReceiptListener(store,json,3,0);
        var channel=mock(Channel.class);var event=event();
        listener.receive(message(event),channel);listener.receive(message(event),channel);
        verify(channel,times(2)).basicAck(7,false);verify(channel,never()).basicNack(anyLong(),anyBoolean(),anyBoolean());
        assertEquals(1,store.findByTenant("tenant").size());assertTrue(store.findByTenant("other").isEmpty());
        var restored=new FileReceiptStore(directory.toString(),json);assertFalse(restored.saveOnce(event));
    }
    @Test void retryRecoversWithoutRequeueAndBeforeAck() throws Exception {
        var store=mock(ReceiptStore.class);var channel=mock(Channel.class);var event=event();
        when(store.saveOnce(event)).thenThrow(new IOException("transient")).thenReturn(true);
        new ReceiptListener(store,json,3,0).receive(message(event),channel);
        var order=inOrder(store,channel);order.verify(store,times(2)).saveOnce(event);order.verify(channel).basicAck(7,false);
        verify(channel,never()).basicNack(anyLong(),anyBoolean(),anyBoolean());
    }
    @Test void retryExhaustionNacksOnceWithoutInfiniteRequeue() throws Exception {
        var store=mock(ReceiptStore.class);var channel=mock(Channel.class);var event=event();
        when(store.saveOnce(event)).thenThrow(new IOException("transient"));
        new ReceiptListener(store,json,3,0).receive(message(event),channel);
        verify(store,times(3)).saveOnce(event);verify(channel).basicNack(7,false,false);verify(channel,never()).basicAck(anyLong(),anyBoolean());
    }
    @Test void invalidContractAndConflictingIdentityGoToDeadLetter() throws Exception {
        var store=new FileReceiptStore(directory.toString(),json);var channel=mock(Channel.class);
        var invalid=new Message("{invalid".getBytes(),new MessageProperties());invalid.getMessageProperties().setDeliveryTag(7);
        new ReceiptListener(store,json,3,0).receive(invalid,channel);
        var event=event();store.saveOnce(event);
        var conflict=new OrderRegisteredV1(1,event.eventId(),event.orderId(),"tenant",event.occurredAt(),new BigDecimal("99.00"),"CLP",1);
        new ReceiptListener(store,json,3,0).receive(message(conflict),channel);
        verify(channel,times(2)).basicNack(7,false,false);verify(channel,never()).basicAck(anyLong(),anyBoolean());
    }
    @Test void ackFailureIsNotMistakenForProcessingFailure() throws Exception {
        var store=new FileReceiptStore(directory.toString(),json);var channel=mock(Channel.class);
        doThrow(new IOException("transport")).when(channel).basicAck(7,false);
        assertThrows(IOException.class,()->new ReceiptListener(store,json,3,0).receive(message(event()),channel));
        verify(channel,never()).basicNack(anyLong(),anyBoolean(),anyBoolean());
        assertEquals(1,store.findByTenant("tenant").size());
    }
}
