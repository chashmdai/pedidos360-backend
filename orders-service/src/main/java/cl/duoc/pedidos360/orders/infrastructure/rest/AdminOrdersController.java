package cl.duoc.pedidos360.orders.infrastructure.rest;

import cl.duoc.pedidos360.orders.application.OrderService;
import cl.duoc.pedidos360.orders.infrastructure.rest.OrdersController.OrderResponse;
import java.util.List;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AdminOrdersController {
    private final OrderService orders;
    public AdminOrdersController(OrderService orders) { this.orders = orders; }

    @GetMapping("/api/v1/admin/pedidos")
    public List<OrderResponse> list(@AuthenticationPrincipal Jwt jwt) {
        // Administration stays inside the verified tenant. /pedidos still means own orders.
        return orders.listForAdministration(jwt.getClaimAsString("tid")).stream().map(OrderResponse::from).toList();
    }
}
