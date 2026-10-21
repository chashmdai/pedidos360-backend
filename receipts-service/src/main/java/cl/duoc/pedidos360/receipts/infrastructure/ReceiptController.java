package cl.duoc.pedidos360.receipts.infrastructure;
import cl.duoc.pedidos360.receipts.application.ReceiptStore;
import cl.duoc.pedidos360.messaging.OrderRegisteredV1;
import java.io.IOException;
import java.util.List;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping("/api/v1/admin/receipts")
public class ReceiptController {
    private final ReceiptStore store;
    public ReceiptController(ReceiptStore store) { this.store=store; }
    @GetMapping public List<OrderRegisteredV1> list(@AuthenticationPrincipal Jwt jwt) throws IOException {
        return store.findByTenant(jwt.getClaimAsString("tid"));
    }
}
