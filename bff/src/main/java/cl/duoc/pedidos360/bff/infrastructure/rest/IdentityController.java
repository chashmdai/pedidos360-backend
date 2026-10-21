package cl.duoc.pedidos360.bff.infrastructure.rest;

import java.time.Instant;
import java.util.Arrays;
import java.util.List;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {
    @GetMapping("/api/v1/me")
    ResponseEntity<IdentityResponse> me(@AuthenticationPrincipal Jwt jwt) {
        var roles = jwt.getClaimAsStringList("roles");
        var scopes = jwt.getClaimAsString("scp");
        // Only a deliberate allowlist of verified API claims. Never return bearer tokens.
        var identity = new IdentityResponse(jwt.getClaimAsString("name"), jwt.getClaimAsString("preferred_username"),
            jwt.getClaimAsString("tid"), jwt.getClaimAsString("oid"), jwt.getSubject(), jwt.getIssuer().toString(),
            jwt.getAudience(), jwt.getClaimAsString("azp"), jwt.getClaimAsString("ver"),
            roles == null ? List.of() : roles,
            scopes == null ? List.of() : Arrays.stream(scopes.split(" ")).filter(s -> !s.isBlank()).toList(),
            jwt.getIssuedAt(), jwt.getExpiresAt());
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(identity);
    }
    public record IdentityResponse(String name, String username, String tenantId, String subjectId, String tokenSubject,
                                   String issuer, List<String> audience, String clientId, String tokenVersion,
                                   List<String> roles, List<String> scopes, Instant issuedAt, Instant expiresAt) {}
}
