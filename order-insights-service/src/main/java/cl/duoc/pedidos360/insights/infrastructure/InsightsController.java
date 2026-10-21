package cl.duoc.pedidos360.insights.infrastructure;
import cl.duoc.pedidos360.insights.application.ProjectionStore;
import cl.duoc.pedidos360.insights.sales.SalesSummary;
import java.io.IOException;
import java.time.ZoneOffset;
import java.util.*;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping("/api/v1/admin/insights")
public class InsightsController {
    private final ProjectionStore audit,sales;
    public InsightsController(@Qualifier("auditStore") ProjectionStore audit,@Qualifier("salesStore") ProjectionStore sales) { this.audit=audit;this.sales=sales; }
    @GetMapping("/audit") public Object audit(@AuthenticationPrincipal Jwt jwt) throws IOException {
        return audit.findByTenant(jwt.getClaimAsString("tid"));
    }
    @GetMapping("/sales") public Object sales(@AuthenticationPrincipal Jwt jwt) throws IOException {
        return SalesSummary.summarize(sales.findByTenant(jwt.getClaimAsString("tid")).stream()
            .map(e -> new SalesSummary.Sale(e.occurredAt().atZone(ZoneOffset.UTC).toLocalDate(),e.currency(),e.total())).toList());
    }
}
