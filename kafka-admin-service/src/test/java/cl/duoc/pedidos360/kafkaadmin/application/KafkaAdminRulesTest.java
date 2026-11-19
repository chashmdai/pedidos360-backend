package cl.duoc.pedidos360.kafkaadmin.application;

import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import org.apache.kafka.common.errors.*;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

class KafkaAdminRulesTest {
    static HttpStatus statusOf(Runnable action) {
        return HttpStatus.valueOf(assertThrows(ResponseStatusException.class, action::run).getStatusCode().value());
    }

    @Test void whitelistMatchesTable14() {
        assertEquals(java.util.Set.of("retention.ms", "cleanup.policy", "min.insync.replicas", "segment.ms", "max.message.bytes"), KafkaAdminService.CONFIG_WHITELIST);
    }

    @Test void onlyWhitelistedConfigsWithBoundedValuesAreAccepted() {
        assertEquals(Map.of("retention.ms", "3600000", "cleanup.policy", "compact"), KafkaAdminService.validConfigs(Map.of("retention.ms", "3600000", "cleanup.policy", "compact")));
        assertEquals(Map.of("retention.ms", "-1"), KafkaAdminService.validConfigs(Map.of("retention.ms", "-1")));
        assertEquals(HttpStatus.BAD_REQUEST, statusOf(() -> KafkaAdminService.validConfigs(Map.of("compression.type", "lz4"))), "not whitelisted");
        assertEquals(HttpStatus.BAD_REQUEST, statusOf(() -> KafkaAdminService.validConfigs(Map.of("unclean.leader.election.enable", "true"))));
        assertEquals(HttpStatus.BAD_REQUEST, statusOf(() -> KafkaAdminService.validConfigs(Map.of("retention.ms", "1000"))), "below one minute");
        assertEquals(HttpStatus.BAD_REQUEST, statusOf(() -> KafkaAdminService.validConfigs(Map.of("cleanup.policy", "purge"))));
        assertEquals(HttpStatus.BAD_REQUEST, statusOf(() -> KafkaAdminService.validConfigs(Map.of("min.insync.replicas", "4"))));
        assertEquals(HttpStatus.BAD_REQUEST, statusOf(() -> KafkaAdminService.validConfigs(Map.of("max.message.bytes", "abc"))));
    }

    @Test void kafkaErrorsMapToTheReportStatusCodes() {
        assertEquals(HttpStatus.NOT_FOUND, HttpStatus.valueOf(KafkaAdminService.translate(new UnknownTopicOrPartitionException("x")).getStatusCode().value()));
        assertEquals(HttpStatus.CONFLICT, HttpStatus.valueOf(KafkaAdminService.translate(new TopicExistsException("x")).getStatusCode().value()));
        assertEquals(HttpStatus.BAD_REQUEST, HttpStatus.valueOf(KafkaAdminService.translate(new InvalidReplicationFactorException("x")).getStatusCode().value()));
        assertEquals(HttpStatus.BAD_REQUEST, HttpStatus.valueOf(KafkaAdminService.translate(new InvalidPartitionsException("x")).getStatusCode().value()));
        assertEquals(HttpStatus.SERVICE_UNAVAILABLE, HttpStatus.valueOf(KafkaAdminService.translate(new TimeoutException("x")).getStatusCode().value()));
        assertEquals(HttpStatus.SERVICE_UNAVAILABLE, HttpStatus.valueOf(KafkaAdminService.translate(new DisconnectException("x")).getStatusCode().value()));
    }
}
