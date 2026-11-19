package cl.duoc.pedidos360.kafkaadmin.api;

import cl.duoc.pedidos360.kafkaadmin.api.AdminRequests.*;
import cl.duoc.pedidos360.kafkaadmin.application.KafkaAdminService;
import cl.duoc.pedidos360.kafkaadmin.application.KafkaAdminService.*;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/** Report table 14 under /api/v1/admin/kafka (contracts/kafka-admin-openapi.yaml). */
@RestController
@RequestMapping("/api/v1/admin/kafka")
public class KafkaAdminController {
    private final KafkaAdminService service;

    public KafkaAdminController(KafkaAdminService service) { this.service = service; }

    @GetMapping("/cluster") public Cluster cluster() { return service.cluster(); }

    @GetMapping("/topics") public List<TopicSummary> topics(@RequestParam(defaultValue = "false") boolean includeInternal) {
        return service.topics(includeInternal);
    }

    @GetMapping("/topics/{name}") public TopicDetail topic(@PathVariable String name) { return service.topic(name); }

    @PostMapping("/topics") public ResponseEntity<TopicDetail> create(@Valid @RequestBody CreateTopic request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(service.create(request));
    }

    @PatchMapping("/topics/{name}/configs") public TopicDetail configs(@PathVariable String name, @Valid @RequestBody UpdateConfigs request) {
        return service.updateConfigs(name, request.configs());
    }

    @PostMapping("/topics/{name}/partitions") public TopicDetail partitions(@PathVariable String name, @Valid @RequestBody IncreasePartitions request) {
        return service.increasePartitions(name, request.partitions());
    }

    @DeleteMapping("/topics/{name}") @ResponseStatus(HttpStatus.NO_CONTENT) public void delete(@PathVariable String name) { service.delete(name); }

    @GetMapping("/consumer-groups") public List<GroupSummary> groups() { return service.groups(); }

    @GetMapping("/consumer-groups/{groupId}") public GroupDetail group(@PathVariable String groupId) { return service.group(groupId); }
}
