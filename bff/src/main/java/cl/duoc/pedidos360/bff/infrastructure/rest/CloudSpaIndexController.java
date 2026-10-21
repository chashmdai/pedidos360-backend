package cl.duoc.pedidos360.bff.infrastructure.rest;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
@Controller
@ConditionalOnProperty(name="pedidos.spa.enabled",havingValue="true")
public class CloudSpaIndexController {
    // ResourceHttpRequestHandler rejects an empty resource path before invoking its resolver.
    @GetMapping({"/app","/app/"}) public String index() { return "forward:/app/index.html"; }
}
