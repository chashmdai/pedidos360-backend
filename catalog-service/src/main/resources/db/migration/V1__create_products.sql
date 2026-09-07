CREATE TABLE products (
 id VARCHAR(36) PRIMARY KEY,
 name VARCHAR(120) NOT NULL,
 description VARCHAR(500) NOT NULL,
 price DECIMAL(19,2) NOT NULL,
 currency VARCHAR(3) NOT NULL,
 stock INT NOT NULL,
 active BOOLEAN NOT NULL,
 CONSTRAINT ck_product_price CHECK (price >= 0),
 CONSTRAINT ck_product_stock CHECK (stock >= 0)
);
