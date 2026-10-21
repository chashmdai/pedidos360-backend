package cl.duoc.pedidos360.insights;
import cl.duoc.pedidos360.insights.application.ProjectionStore;
import cl.duoc.pedidos360.insights.audit.AuditListener;
import cl.duoc.pedidos360.insights.sales.*;
import cl.duoc.pedidos360.insights.infrastructure.*;
import cl.duoc.pedidos360.messaging.OrderRegisteredV1;
import com.rabbitmq.client.Channel;
import java.io.IOException;
import java.math.BigDecimal;
import java.nio.file.Path;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import org.springframework.amqp.core.*;
import tools.jackson.databind.json.JsonMapper;

class ProjectionConsumerTest {
    @TempDir Path directory;
    final JsonMapper json=new JsonMapper();
    OrderRegisteredV1 event() { return new OrderRegisteredV1(1,UUID.randomUUID(),UUID.randomUUID(),"tenant",Instant.now(),new BigDecimal("12.50"),"CLP",2); }
    Message message(OrderRegisteredV1 event) {
        var properties=new MessageProperties();properties.setMessageId(event.eventId().toString());properties.setDeliveryTag(9);
        return new Message(json.writeValueAsBytes(event),properties);
    }
    ManualProjectionConsumer listener(String flow,ProjectionStore store) {
        return flow.equals("audit")?new AuditListener(store,json,3,0):new SalesListener(store,json,3,0);
    }
    @ParameterizedTest @ValueSource(strings={"audit","sales"})
    void durableEffectBeforeAckAndIdempotentAcrossRestart(String flow) throws Exception {
        var files=new FileProjectionStore(directory,json);var consumer=listener(flow,files);var channel=mock(Channel.class);var event=event();
        consumer.receive(message(event),channel);consumer.receive(message(event),channel);
        verify(channel,times(2)).basicAck(9,false);verify(channel,never()).basicNack(anyLong(),anyBoolean(),anyBoolean());
        var restored=new FileProjectionStore(directory,json);
        assertFalse(restored.saveOnce(event));assertEquals(1,restored.findByTenant("tenant").size());assertTrue(restored.findByTenant("other").isEmpty());
    }
    @ParameterizedTest @ValueSource(strings={"audit","sales"})
    void transientFailureRetriesThenAcksOnlyAfterRecovery(String flow) throws Exception {
        var store=mock(ProjectionStore.class);var channel=mock(Channel.class);var event=event();
        when(store.saveOnce(event)).thenThrow(new IOException("temporary")).thenReturn(true);
        listener(flow,store).receive(message(event),channel);
        var sequence=inOrder(store,channel);sequence.verify(store,times(2)).saveOnce(event);sequence.verify(channel).basicAck(9,false);
        verify(channel,never()).basicNack(anyLong(),anyBoolean(),anyBoolean());
    }
    @ParameterizedTest @ValueSource(strings={"audit","sales"})
    void exhaustedRetriesNackWithoutRequeue(String flow) throws Exception {
        var store=mock(ProjectionStore.class);var channel=mock(Channel.class);var event=event();
        when(store.saveOnce(event)).thenThrow(new IOException("temporary"));
        listener(flow,store).receive(message(event),channel);
        verify(store,times(3)).saveOnce(event);verify(channel).basicNack(9,false,false);verify(channel,never()).basicAck(anyLong(),anyBoolean());
    }
    @ParameterizedTest @ValueSource(strings={"audit","sales"})
    void malformedAndPermanentConflictNackWithoutRetry(String flow) throws Exception {
        var store=new FileProjectionStore(directory,json);var channel=mock(Channel.class);var event=event();store.saveOnce(event);
        var malformed=new Message("{".getBytes(),new MessageProperties());malformed.getMessageProperties().setDeliveryTag(9);
        listener(flow,store).receive(malformed,channel);
        var conflict=new OrderRegisteredV1(1,event.eventId(),event.orderId(),event.tenantId(),event.occurredAt(),new BigDecimal("99.00"),"CLP",2);
        listener(flow,store).receive(message(conflict),channel);
        verify(channel,times(2)).basicNack(9,false,false);verify(channel,never()).basicAck(anyLong(),anyBoolean());
        assertEquals(event,store.findByTenant("tenant").getFirst());
    }
    @ParameterizedTest @ValueSource(strings={"audit","sales"})
    void ackTransportFailureEscapesForRedelivery(String flow) throws Exception {
        var store=new FileProjectionStore(directory,json);var channel=mock(Channel.class);
        doThrow(new IOException("transport")).when(channel).basicAck(9,false);
        assertThrows(IOException.class,()->listener(flow,store).receive(message(event()),channel));
        verify(channel,never()).basicNack(anyLong(),anyBoolean(),anyBoolean());assertEquals(1,store.findByTenant("tenant").size());
    }
    @Test void summaryGroupsDayAndCurrencyWithoutRoundingOrMixedCurrencies() {
        LocalDate day=LocalDate.of(2026,10,21);
        var result=SalesSummary.summarize(List.of(new SalesSummary.Sale(day,"CLP",new BigDecimal("12.50")),new SalesSummary.Sale(day,"CLP",new BigDecimal("0.10")),new SalesSummary.Sale(day,"USD",new BigDecimal("1.00")),new SalesSummary.Sale(day.plusDays(1),"CLP",BigDecimal.ONE)));
        assertEquals(3,result.size());assertEquals(new BigDecimal("12.60"),result.getFirst().total());assertEquals(2,result.getFirst().orders());
    }
}
