package cl.duoc.pedidos360.rabbitadmin;
import cl.duoc.pedidos360.rabbitadmin.api.AdminRequests.*;
import cl.duoc.pedidos360.rabbitadmin.application.RabbitAdminService;
import jakarta.validation.Validation;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;
class AdminValidationTest {
    @Test void rejectsEmptyNamesInvalidTypesAndUnsafeArguments() {
        try (var factory=Validation.buildDefaultValidatorFactory()) {
            var validator=factory.getValidator();
            assertFalse(validator.validate(new QueueRequest("",true,false,-1,0)).isEmpty());
            assertFalse(validator.validate(new QueueRequest("pedidos360.lab.ok",null,false,null,null)).isEmpty());
            assertFalse(validator.validate(new ExchangeRequest("pedidos360.lab.ok","invalid",true,false)).isEmpty());
            assertFalse(validator.validate(new BindingRequest("ok","ok","")).isEmpty());
            assertTrue(validator.validate(new QueueRequest("pedidos360.lab.ok",true,false,1000,10)).isEmpty());
        }
    }
    @Test void criticalNamespacesAreRejectedBeforeAnyBrokerCall() {
        var broker=mock(RestClient.class);var service=new RabbitAdminService(broker,"pedidos360-ep3","pedidos360.lab.");
        var denied=assertThrows(ResponseStatusException.class,()->service.deleteQueue("pedidos360.receipts.failed.v1"));
        assertEquals(403,denied.getStatusCode().value());verifyNoInteractions(broker);
    }
}
