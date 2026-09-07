CREATE TABLE purchase_orders (
 id VARCHAR(36) PRIMARY KEY,
 owner_tenant VARCHAR(100) NOT NULL,
 owner_subject VARCHAR(100) NOT NULL,
 status VARCHAR(20) NOT NULL,
 created_at DATETIME(6) NOT NULL,
 INDEX ix_orders_owner (owner_tenant, owner_subject, created_at)
);
CREATE TABLE order_items (
 id BIGINT AUTO_INCREMENT PRIMARY KEY,
 order_id VARCHAR(36) NOT NULL,
 product_id VARCHAR(36) NOT NULL,
 product_name VARCHAR(120) NOT NULL,
 unit_price DECIMAL(19,2) NOT NULL,
 currency VARCHAR(3) NOT NULL,
 quantity INT NOT NULL,
 CONSTRAINT fk_items_order FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
 CONSTRAINT uq_order_product UNIQUE (order_id, product_id),
 CONSTRAINT ck_item_quantity CHECK (quantity BETWEEN 1 AND 1000),
 CONSTRAINT ck_item_price CHECK (unit_price >= 0)
);
