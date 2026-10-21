"""Check only pedidos360-mysql. Credentials are read inside that container."""
import json
import subprocess


def sql(secret, user, statement):
    return subprocess.run([
        "docker", "exec", "-i", "pedidos360-mysql", "bash", "-c",
        'export MYSQL_PWD="$(cat /run/secrets/"$1")"; exec mysql --protocol=tcp --host=127.0.0.1 --user="$2" --batch --skip-column-names',
        "pedidos360-check", secret, user,
    ], input=statement, text=True, capture_output=True)


result = sql("mysql_root", "root", "SELECT VERSION(); SELECT 'catalog', version, description, success FROM pedidos360_catalog.flyway_schema_history UNION ALL SELECT 'orders', version, description, success FROM pedidos360_orders.flyway_schema_history;")
assert result.returncode == 0, "Could not inspect Pedidos360 migration history"
print(result.stdout.strip())
checks = []
for context, other, table in [("catalog", "orders", "products"), ("orders", "catalog", "purchase_orders")]:
    for role in ["app", "migration"]:
        secret = context + "_" + role
        user = f"pedidos360_{context}_{role}"
        own = sql(secret, user, f"SELECT COUNT(*) FROM pedidos360_{context}.{table};")
        assert own.returncode == 0, f"{user} cannot read its own data"
        foreign = sql(secret, user, f"SELECT * FROM pedidos360_{other}.flyway_schema_history LIMIT 1;")
        assert foreign.returncode != 0 and "ERROR 1142" in foreign.stderr, f"Isolation failed: {user}"
        checks.append({"user": user, "own_schema": "PASS", "other_schema": "DENIED (1142)"})
        if role == "app":
            ddl = sql(secret, user, f"CREATE TABLE pedidos360_{context}.pedidos360_privilege_probe (id INT);")
            if ddl.returncode == 0:
                sql(context + "_migration", f"pedidos360_{context}_migration", f"DROP TABLE pedidos360_{context}.pedidos360_privilege_probe;")
                raise AssertionError(f"Application DDL isolation failed: {user}")
            assert "ERROR 1142" in ddl.stderr, "DDL rejected for an unexpected reason"
            checks[-1]["application_ddl"] = "DENIED (1142)"
print(json.dumps({"result": "PASS", "checks": checks}, indent=2))
