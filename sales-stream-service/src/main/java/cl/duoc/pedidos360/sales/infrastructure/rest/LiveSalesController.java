package cl.duoc.pedidos360.sales.infrastructure.rest;

import cl.duoc.pedidos360.sales.application.LiveSalesView;
import cl.duoc.pedidos360.sales.domain.OrderAlert;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** GET /api/v1/ventas/en-vivo (contracts/live-sales-response-v1.schema.json). Aggregated per tenant; no personal data. */
@RestController
public class LiveSalesController {
    public record Producto(UUID productoId, String nombre, String moneda, long unidades, long pedidos, BigDecimal importe,
                           long version, Instant actualizadoEn) {}
    public record Alerta(UUID pedidoId, List<String> motivos, BigDecimal total, String moneda, int lineas,
                         Instant ocurridoEn, Instant detectadaEn) {}
    public record VentasEnVivo(LocalDate fecha, Instant generadoEn, Instant ultimaActualizacion,
                               List<Producto> productos, List<Alerta> alertas) {}

    private final LiveSalesView view;

    public LiveSalesController(LiveSalesView view) { this.view = view; }

    static String motivo(OrderAlert.Reason reason) {
        return switch (reason) { case HIGH_VALUE -> "ALTO_VALOR"; case MANY_LINES -> "MUCHAS_LINEAS"; };
    }

    @GetMapping("/api/v1/ventas/en-vivo")
    ResponseEntity<VentasEnVivo> live(@AuthenticationPrincipal Jwt jwt) {
        // Tenant always comes from the validated token, never from the request.
        var snapshot = view.snapshot(jwt.getClaimAsString("tid"));
        var productos = snapshot.products().stream().map(p -> new Producto(p.key().productId(), p.productName(), p.key().currency(),
                p.unitsSold(), p.ordersCount(), p.revenue(), p.version(), p.updatedAt())).toList();
        var alertas = snapshot.alerts().stream().map(a -> new Alerta(a.orderId(),
                a.reasons().stream().sorted().map(LiveSalesController::motivo).toList(), a.total(), a.currency(), a.lineCount(),
                a.occurredAt(), a.detectedAt())).toList();
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
                .body(new VentasEnVivo(snapshot.businessDate(), snapshot.generatedAt(), snapshot.lastUpdate(), productos, alertas));
    }
}
