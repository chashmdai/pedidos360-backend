package cl.duoc.pedidos360.rabbitadmin.api;
import jakarta.validation.constraints.*;
public final class AdminRequests {
    private AdminRequests() {}
    public record QueueRequest(
        @NotBlank @Pattern(regexp="[a-zA-Z0-9][a-zA-Z0-9._-]{0,100}") String name,
        @NotNull Boolean durable, @NotNull Boolean autoDelete,
        @Min(100) @Max(86400000) Integer messageTtl, @Min(1) @Max(10000) Integer maxLength) {}
    public record ExchangeRequest(
        @NotBlank @Pattern(regexp="[a-zA-Z0-9][a-zA-Z0-9._-]{0,100}") String name,
        @NotBlank @Pattern(regexp="direct|topic|fanout") String type,
        @NotNull Boolean durable, @NotNull Boolean autoDelete) {}
    public record BindingRequest(
        @NotBlank @Pattern(regexp="[a-zA-Z0-9][a-zA-Z0-9._-]{0,100}") String exchange,
        @NotBlank @Pattern(regexp="[a-zA-Z0-9][a-zA-Z0-9._-]{0,100}") String queue,
        @NotBlank @Pattern(regexp="[a-zA-Z0-9.*#_-]{1,100}") String routingKey) {}
    public record QueuePolicyRequest(
        @Min(100) @Max(86400000) Integer messageTtl,
        @Min(1) @Max(10000) Integer maxLength) {
        @AssertTrue(message="Provide at least one bounded policy setting")
        public boolean isSettingProvided() { return messageTtl!=null || maxLength!=null; }
    }
}
