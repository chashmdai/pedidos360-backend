package cl.duoc.pedidos360.orders.domain;
public record OwnerId(String tenant, String subject) {
    public OwnerId {
        if (tenant == null || tenant.isBlank() || subject == null || subject.isBlank())
            throw new IllegalArgumentException("El propietario es obligatorio.");
    }
}
