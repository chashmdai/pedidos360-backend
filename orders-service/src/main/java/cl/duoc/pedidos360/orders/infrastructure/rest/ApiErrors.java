package cl.duoc.pedidos360.orders.infrastructure.rest;
import java.util.NoSuchElementException;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestClientException;

@RestControllerAdvice
public class ApiErrors {
    @ExceptionHandler(NoSuchElementException.class)
    ProblemDetail notFound(NoSuchElementException exception) {
        return ProblemDetail.forStatusAndDetail(HttpStatus.NOT_FOUND, "El recurso no existe o no está disponible.");
    }
    @ExceptionHandler(IllegalArgumentException.class)
    ProblemDetail invalid(IllegalArgumentException exception) {
        return ProblemDetail.forStatusAndDetail(HttpStatus.BAD_REQUEST, exception.getMessage());
    }
    @ExceptionHandler(RestClientException.class)
    ProblemDetail dependency(RestClientException exception) {
        return ProblemDetail.forStatusAndDetail(HttpStatus.BAD_GATEWAY, "No fue posible consultar el servicio requerido. Intenta nuevamente.");
    }
}
