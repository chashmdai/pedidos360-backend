package cl.duoc.pedidos360.orders.domain;
import java.util.*;
public record OrderItem(UUID productId, String productName, Money unitPrice, int quantity) {
    public OrderItem {
        Objects.requireNonNull(productId);
        Objects.requireNonNull(unitPrice);
        if (productName == null || productName.isBlank() || quantity < 1 || quantity > 1000)
            throw new IllegalArgumentException("La línea de pedido no es válida.");
    }
    public Money subtotal() { return unitPrice.multiply(quantity); }
}
