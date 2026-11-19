-- EP5 schema pedidos360_streams (own application and migration users, like Catalog and Orders).
-- Idempotency: one row per processed eventId; inserted in the same transaction as the accumulators.
CREATE TABLE processed_stream_event (
 event_id VARCHAR(36) PRIMARY KEY,
 order_id VARCHAR(36) NOT NULL,
 consumer_group VARCHAR(100) NOT NULL,
 processed_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
);
-- Daily accumulator per tenant, product, UTC day and currency. version grows by one per applied event.
CREATE TABLE product_sales_daily (
 tenant_id VARCHAR(100) NOT NULL,
 product_id VARCHAR(36) NOT NULL,
 business_date DATE NOT NULL,
 currency CHAR(3) NOT NULL,
 product_name VARCHAR(120) NOT NULL,
 units_sold BIGINT NOT NULL,
 orders_count BIGINT NOT NULL,
 revenue DECIMAL(19,2) NOT NULL,
 version BIGINT NOT NULL,
 last_event_id VARCHAR(36) NOT NULL,
 updated_at TIMESTAMP(6) NOT NULL,
 PRIMARY KEY (tenant_id, product_id, business_date, currency),
 INDEX ix_sales_daily_date (tenant_id, business_date)
);
