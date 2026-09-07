package cl.duoc.pedidos360.catalog.domain;
import java.math.BigDecimal;
import java.util.Objects;
import java.util.UUID;
public record Product(UUID id, String name, String description, BigDecimal price, String currency, int stock, boolean active) {
    public Product {
        Objects.requireNonNull(id);
        if (name == null || name.isBlank() || price == null || price.signum() < 0 || stock < 0)
            throw new IllegalArgumentException("Producto inválido.");
        java.util.Currency.getInstance(currency);
    }
}
