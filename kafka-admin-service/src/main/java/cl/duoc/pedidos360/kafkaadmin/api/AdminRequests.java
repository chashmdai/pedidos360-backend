package cl.duoc.pedidos360.kafkaadmin.api;

import jakarta.validation.constraints.*;
import java.util.Map;

/** Bean Validation of request bodies (report table 14). Namespace and whitelist rules live in the application service. */
public final class AdminRequests {
    private AdminRequests() {}

    public record CreateTopic(
            @NotBlank @Pattern(regexp = "[a-zA-Z0-9._-]{1,249}") String name,
            @NotNull @Min(1) @Max(12) Integer partitions,
            @NotNull @Min(1) @Max(3) Integer replicationFactor,
            Map<@NotBlank String, @NotBlank String> configs) {}

    public record UpdateConfigs(@NotEmpty Map<@NotBlank String, @NotBlank String> configs) {}

    public record IncreasePartitions(@NotNull @Min(1) @Max(12) Integer partitions) {}
}
