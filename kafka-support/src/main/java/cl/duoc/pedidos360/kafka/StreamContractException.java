package cl.duoc.pedidos360.kafka;

/** A payload that violates a streaming contract. Never retried: it goes to the DLT. */
public class StreamContractException extends IllegalArgumentException {
    public StreamContractException(String message) { super(message); }
}
