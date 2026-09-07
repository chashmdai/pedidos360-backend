package cl.duoc.pedidos360.orders;
import com.nimbusds.jose.*;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.*;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.*;
import com.sun.net.httpserver.HttpServer;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.*;

final class TestTokens implements AutoCloseable {
    static final String AUDIENCE="pedidos360-test-api";
    private final RSAKey key;
    private final HttpServer server;
    TestTokens() {
        try {
            key=new RSAKeyGenerator(2048).keyID("test-key").generate();
            server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
            server.createContext("/jwks",exchange -> {
                var body=new JWKSet(key.toPublicJWK()).toString().getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set("Content-Type","application/json");
                exchange.sendResponseHeaders(200,body.length); exchange.getResponseBody().write(body); exchange.close();
            });
            server.start();
        } catch (Exception e) { throw new IllegalStateException(e); }
    }
    String issuer() { return "http://127.0.0.1:"+server.getAddress().getPort(); }
    String token(String subject,String scopes) { return token(subject,scopes,AUDIENCE,issuer(),600); }
    String token(String subject,String scopes,String audience,String issuer,long ttl) {
        try {
            var claims=new JWTClaimsSet.Builder().issuer(issuer).audience(audience).subject(subject)
                .claim("azp","test-spa").claim("ver","2.0").claim("tid","test-tenant").claim("oid",subject).claim("scp",scopes).claim("roles",List.of("User"))
                .issueTime(Date.from(Instant.now().minusSeconds(1))).notBeforeTime(Date.from(Instant.now().minusSeconds(1)))
                .expirationTime(Date.from(Instant.now().plusSeconds(ttl))).build();
            var signed=new SignedJWT(new JWSHeader.Builder(JWSAlgorithm.RS256).keyID(key.getKeyID()).build(),claims);
            signed.sign(new RSASSASigner(key)); return signed.serialize();
        } catch (Exception e) { throw new IllegalStateException(e); }
    }
    String withClaims(String subject, String scopes, java.util.Map<String,Object> overrides) {
        try {
            var claims = new JWTClaimsSet.Builder(SignedJWT.parse(token(subject, scopes)).getJWTClaimsSet());
            overrides.forEach(claims::claim);
            var signed = new SignedJWT(new JWSHeader.Builder(JWSAlgorithm.RS256).keyID(key.getKeyID()).build(), claims.build());
            signed.sign(new RSASSASigner(key));
            return signed.serialize();
        } catch (Exception e) { throw new IllegalStateException(e); }
    }
    public void close() { server.stop(0); }
}
