#!/bin/bash
# Works both sourced and executable (DrvFS does not preserve the executable bit).
set -euo pipefail
catalog_app=$(cat /run/secrets/catalog_app)
catalog_migration=$(cat /run/secrets/catalog_migration)
orders_app=$(cat /run/secrets/orders_app)
orders_migration=$(cat /run/secrets/orders_migration)
# Passwords are generated as hexadecimal; never insert arbitrary input into SQL.
for value in "$catalog_app" "$catalog_migration" "$orders_app" "$orders_migration"; do
  [[ "$value" =~ ^[a-f0-9]{48}$ ]] || { echo "Invalid local secret format" >&2; exit 1; }
done
MYSQL_PWD="$(cat /run/secrets/mysql_root)" mysql --user=root <<SQL
CREATE DATABASE IF NOT EXISTS pedidos360_catalog CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS pedidos360_orders CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'pedidos360_catalog_app'@'%' IDENTIFIED BY '$catalog_app';
CREATE USER IF NOT EXISTS 'pedidos360_catalog_migration'@'%' IDENTIFIED BY '$catalog_migration';
CREATE USER IF NOT EXISTS 'pedidos360_orders_app'@'%' IDENTIFIED BY '$orders_app';
CREATE USER IF NOT EXISTS 'pedidos360_orders_migration'@'%' IDENTIFIED BY '$orders_migration';
GRANT SELECT,INSERT,UPDATE,DELETE ON pedidos360_catalog.* TO 'pedidos360_catalog_app'@'%';
GRANT ALL PRIVILEGES ON pedidos360_catalog.* TO 'pedidos360_catalog_migration'@'%';
GRANT SELECT,INSERT,UPDATE,DELETE ON pedidos360_orders.* TO 'pedidos360_orders_app'@'%';
GRANT ALL PRIVILEGES ON pedidos360_orders.* TO 'pedidos360_orders_migration'@'%';
SQL
unset catalog_app catalog_migration orders_app orders_migration value
