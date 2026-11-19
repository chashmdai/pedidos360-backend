package cl.duoc.pedidos360.kafkaadmin.security;

import java.util.ArrayList;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.*;
import org.springframework.security.oauth2.jwt.*;
import org.springframework.security.oauth2.server.resource.authentication.*;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {
    @Bean
    JwtDecoder jwtDecoder(@Value("${pedidos.security.issuer}") String issuer,
                          @Value("${pedidos.security.audience}") String audience,
                          @Value("${pedidos.security.jwks}") String jwks,
                          @Value("${pedidos.security.tenant}") String tenant,
                          @Value("${pedidos.security.client}") String client) {
        var decoder = NimbusJwtDecoder.withJwkSetUri(jwks).build();
        OAuth2TokenValidator<Jwt> claims = jwt -> {
            boolean valid = jwt.getAudience() != null && jwt.getAudience().contains(audience)
                && tenant.equals(jwt.getClaimAsString("tid"))
                && client.equals(jwt.getClaimAsString("azp"))
                && "2.0".equals(jwt.getClaimAsString("ver"))
                && jwt.getExpiresAt() != null
                && jwt.getClaimAsString("oid") != null && !jwt.getClaimAsString("oid").isBlank();
            return valid ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(new OAuth2Error("invalid_token", "Invalid API audience, tenant, client, token version, expiry or user identity", null));
        };
        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(JwtValidators.createDefaultWithIssuer(issuer), claims));
        return decoder;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        var converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(jwt -> {
            List<GrantedAuthority> authorities = new ArrayList<>(new JwtGrantedAuthoritiesConverter().convert(jwt));
            List<String> roles = jwt.getClaimAsStringList("roles");
            if (roles != null) roles.forEach(role -> authorities.add(new SimpleGrantedAuthority("ROLE_" + role)));
            return authorities;
        });
        return http.csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                // Same rule as rabbit-admin-service: role Admin AND scope Orders.Read (a role never replaces a scope).
                .requestMatchers("/api/v1/admin/kafka/**").access(new org.springframework.security.web.access.expression.WebExpressionAuthorizationManager(
                    "hasRole('Admin') and hasAuthority('SCOPE_Orders.Read')"))
                .anyRequest().denyAll())
            .oauth2ResourceServer(server -> server.jwt(jwt -> jwt.jwtAuthenticationConverter(converter)))
            .build();
    }
}
