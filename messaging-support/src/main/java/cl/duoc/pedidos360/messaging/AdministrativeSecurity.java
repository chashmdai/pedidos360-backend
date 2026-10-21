package cl.duoc.pedidos360.messaging;

import java.util.ArrayList;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.*;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.*;
import org.springframework.security.oauth2.jwt.*;
import org.springframework.security.oauth2.server.resource.authentication.*;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.expression.WebExpressionAuthorizationManager;

/** Same token constraints as the existing services; administrative access remains explicit. */
@Configuration(proxyBeanMethods=false)
public class AdministrativeSecurity {
    @Bean JwtDecoder jwtDecoder(@Value("${pedidos.security.issuer}") String issuer,
            @Value("${pedidos.security.audience}") String audience, @Value("${pedidos.security.jwks}") String jwks,
            @Value("${pedidos.security.tenant}") String tenant, @Value("${pedidos.security.client}") String client) {
        var decoder = NimbusJwtDecoder.withJwkSetUri(jwks).build();
        OAuth2TokenValidator<Jwt> claims = jwt -> jwt.getAudience() != null && jwt.getAudience().contains(audience)
                && tenant.equals(jwt.getClaimAsString("tid")) && client.equals(jwt.getClaimAsString("azp"))
                && "2.0".equals(jwt.getClaimAsString("ver")) && jwt.getExpiresAt() != null
                && jwt.getClaimAsString("oid") != null && !jwt.getClaimAsString("oid").isBlank()
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(new OAuth2Error("invalid_token"));
        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(JwtValidators.createDefaultWithIssuer(issuer), claims));
        return decoder;
    }
    @Bean SecurityFilterChain security(HttpSecurity http) throws Exception {
        var converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(jwt -> {
            List<GrantedAuthority> result = new ArrayList<>(new JwtGrantedAuthoritiesConverter().convert(jwt));
            List<String> roles = jwt.getClaimAsStringList("roles");
            if (roles != null) roles.forEach(role -> result.add(new SimpleGrantedAuthority("ROLE_" + role)));
            return result;
        });
        return http.csrf(csrf -> csrf.disable())
                .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth.requestMatchers("/actuator/health").permitAll()
                    .requestMatchers("/api/v1/rabbit/**", "/api/v1/admin/receipts/**").access(
                        new WebExpressionAuthorizationManager("hasRole('Admin') and hasAuthority('SCOPE_Orders.Read')"))
                    .anyRequest().denyAll())
                .oauth2ResourceServer(s -> s.jwt(j -> j.jwtAuthenticationConverter(converter))).build();
    }
}
