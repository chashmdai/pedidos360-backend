#!/usr/bin/env bash
set -euo pipefail
config="${PEDIDOS360_CONFIG_DIR:-$HOME/.config/pedidos360/local}"
umask 077
mkdir -p "$config"
chmod 700 "$config"
for name in mysql-root catalog-app catalog-migration orders-app orders-migration; do
  if [ ! -f "$config/$name-password" ]; then openssl rand -hex 24 > "$config/$name-password"; fi
  # Compose bind-mounted secrets preserve host modes. The mysql UID must read them.
  # Host access remains restricted by the enclosing directory's mode 0700.
  chmod 0444 "$config/$name-password"
done
python3 - "$config" <<'PY'
import pathlib,shlex,sys
root=pathlib.Path(sys.argv[1])
values={'SPRING_PROFILES_ACTIVE':'local'}
for context in ['catalog','orders']:
    upper=context.upper()
    values[upper+'_DB_URL']=f'jdbc:mysql://127.0.0.1:13306/pedidos360_{context}?sslMode=DISABLED&allowPublicKeyRetrieval=true&connectionTimeZone=UTC'
    values[upper+'_DB_USER']=f'pedidos360_{context}_app'
    values[upper+'_DB_PASSWORD']=(root/f'{context}-app-password').read_text().strip()
    values[upper+'_MIGRATION_USER']=f'pedidos360_{context}_migration'
    values[upper+'_MIGRATION_PASSWORD']=(root/f'{context}-migration-password').read_text().strip()
(root/'application.env').write_text(''.join('export '+key+'='+shlex.quote(value)+'\n' for key,value in values.items()))
(root/'application.env').chmod(0o600)
print('Local configuration ready:',root)
PY
