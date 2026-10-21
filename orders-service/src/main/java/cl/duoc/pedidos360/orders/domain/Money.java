package cl.duoc.pedidos360.orders.domain;
import java.math.*;
import java.util.Currency;
public record Money(BigDecimal amount, String currency) {
    public Money {
        if (amount == null || amount.signum() < 0) throw new IllegalArgumentException("El importe no puede ser negativo.");
        Currency.getInstance(currency);
        amount = amount.setScale(2, RoundingMode.UNNECESSARY);
        if (amount.precision() > 19) throw new IllegalArgumentException("Importe fuera de rango.");
    }
    public Money multiply(int quantity) {
        if (quantity <= 0) throw new IllegalArgumentException("La cantidad debe ser positiva.");
        return new Money(amount.multiply(BigDecimal.valueOf(quantity)), currency);
    }
    public Money add(Money other) {
        if (!currency.equals(other.currency)) throw new IllegalArgumentException("Un pedido debe usar una sola moneda.");
        return new Money(amount.add(other.amount),currency);
    }
}
