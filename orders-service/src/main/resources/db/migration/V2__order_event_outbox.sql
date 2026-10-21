CREATE TABLE order_event_outbox (
 event_id VARCHAR(36) PRIMARY KEY,
 order_id VARCHAR(36) NOT NULL,
 payload JSON NOT NULL,
 created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 published_at TIMESTAMP(6) NULL,
 attempts INT NOT NULL DEFAULT 0,
 next_attempt_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 last_error_code VARCHAR(40) NULL,
 INDEX ix_outbox_pending (published_at, next_attempt_at)
);
