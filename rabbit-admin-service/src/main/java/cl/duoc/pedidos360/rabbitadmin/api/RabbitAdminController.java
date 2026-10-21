package cl.duoc.pedidos360.rabbitadmin.api;
import cl.duoc.pedidos360.rabbitadmin.application.RabbitAdminService;
import cl.duoc.pedidos360.rabbitadmin.api.AdminRequests.*;
import jakarta.validation.Valid;
import java.util.*;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping("/api/v1/rabbit")
public class RabbitAdminController {
    private final RabbitAdminService service;
    public RabbitAdminController(RabbitAdminService service) { this.service=service; }
    private ResponseEntity<Object> response(RabbitAdminService.Result result) {
        return ResponseEntity.status(result.created()?HttpStatus.CREATED:HttpStatus.OK).body(result.resource());
    }
    @PostMapping("/queues") public ResponseEntity<Object> createQueue(@Valid @RequestBody QueueRequest dto) { return response(service.createQueue(dto)); }
    @GetMapping("/queues/{name}") public Map<String,Object> queue(@PathVariable String name) { return service.getQueue(name); }
    @PatchMapping("/queues/{name}/policy") public Object updateQueue(@PathVariable String name,@Valid @RequestBody QueuePolicyRequest dto) { return service.updateQueuePolicy(name,dto); }
    @DeleteMapping("/queues/{name}") @ResponseStatus(HttpStatus.NO_CONTENT) public void deleteQueue(@PathVariable String name) { service.deleteQueue(name); }
    @PostMapping("/exchanges") public ResponseEntity<Object> createExchange(@Valid @RequestBody ExchangeRequest dto) { return response(service.createExchange(dto)); }
    @GetMapping("/exchanges/{name}") public Map<String,Object> exchange(@PathVariable String name) { return service.getExchange(name); }
    @DeleteMapping("/exchanges/{name}") @ResponseStatus(HttpStatus.NO_CONTENT) public void deleteExchange(@PathVariable String name) { service.deleteExchange(name); }
    @PostMapping("/bindings") public ResponseEntity<Object> createBinding(@Valid @RequestBody BindingRequest dto) { return response(service.createBinding(dto)); }
    @GetMapping("/bindings/{exchange}/{queue}") public List<Map<String,Object>> bindings(@PathVariable String exchange,@PathVariable String queue) { return service.bindings(exchange,queue); }
    @DeleteMapping("/bindings") @ResponseStatus(HttpStatus.NO_CONTENT) public void deleteBinding(@Valid @RequestBody BindingRequest dto) { service.deleteBinding(dto); }
}
