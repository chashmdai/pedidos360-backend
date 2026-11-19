package cl.duoc.pedidos360.kafka;

import java.math.BigDecimal;

/** Shared validation helpers for the versioned streaming contracts (package-private). */
final class Contracts {
    private Contracts() {}

    static void require(boolean condition, String contract, String rule) {
        if (!condition) throw new StreamContractException("Invalid " + contract + ": " + rule);
    }

    static boolean text(String value, int max) { return value != null && !value.isBlank() && value.length() <= max; }

    static boolean isoCurrency(String value) { return value != null && value.matches("[A-Z]{3}"); }

    /** Non-negative decimal with at most two decimals that fits DECIMAL(19,2). */
    static boolean amount(BigDecimal value) {
        return value != null && value.signum() >= 0 && value.scale() <= 2 && value.precision() - value.scale() <= 17;
    }
}
