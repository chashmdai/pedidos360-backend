-- EP5: streaming outbox, independent of the RabbitMQ outbox (order_event_outbox).
-- Same control structure as V2; written in the same transaction as the order.
CREATE TABLE order_stream_outbox (
 event_id VARCHAR(36) PRIMARY KEY,
 order_id VARCHAR(36) NOT NULL,
 payload JSON NOT NULL,
 created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 published_at TIMESTAMP(6) NULL,
 attempts INT NOT NULL DEFAULT 0,
 next_attempt_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 last_error_code VARCHAR(40) NULL,
 INDEX ix_stream_outbox_pending (published_at, next_attempt_at),
 INDEX ix_stream_outbox_order (order_id)
);
