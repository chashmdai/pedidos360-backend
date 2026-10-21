package cl.duoc.pedidos360.orders.infrastructure.rest;
import cl.duoc.pedidos360.orders.application.OrderService;
import cl.duoc.pedidos360.orders.domain.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.net.URI;
import java.time.Instant;
import java.util.*;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping("/api/v1/pedidos")
public class OrdersController {
    private final OrderService orders;
    public OrdersController(OrderService orders) { this.orders=orders; }
    @GetMapping public List<OrderResponse> list(@AuthenticationPrincipal Jwt jwt) { return orders.list(owner(jwt)).stream().map(OrderResponse::from).toList(); }
    @GetMapping("/{id}") public OrderResponse get(@PathVariable UUID id,@AuthenticationPrincipal Jwt jwt) { return OrderResponse.from(orders.get(id,owner(jwt))); }
    @PostMapping public ResponseEntity<OrderResponse> create(@Valid @RequestBody CreateOrder request,@AuthenticationPrincipal Jwt jwt) {
        var created=orders.create(owner(jwt),request.items().stream().map(i -> new OrderService.RequestedItem(i.productoId(),i.cantidad())).toList());
        return ResponseEntity.created(URI.create("/api/v1/pedidos/"+created.id())).body(OrderResponse.from(created));
    }
    private OwnerId owner(Jwt jwt) { return new OwnerId(jwt.getClaimAsString("tid"),jwt.getClaimAsString("oid")); }
    public record CreateOrder(@NotEmpty @Size(max=50) List<@NotNull @Valid ItemRequest> items) {}
    public record ItemRequest(@NotNull UUID productoId,@Min(1) @Max(1000) int cantidad) {}
    public record ItemResponse(UUID productoId,String nombre,BigDecimal precioUnitario,int cantidad,BigDecimal subtotal) {}
    public record OrderResponse(UUID id,String estado,Instant fechaCreacion,List<ItemResponse> items,BigDecimal total,String moneda) {
        static OrderResponse from(Order order) {
            return new OrderResponse(order.id(),order.status().name(),order.createdAt(),
                order.items().stream().map(i -> new ItemResponse(i.productId(),i.productName(),i.unitPrice().amount(),i.quantity(),i.subtotal().amount())).toList(),
                order.total().amount(),order.total().currency());
        }
    }
}
