#!/usr/bin/env bash
# Runs only on the new, dedicated Pedidos360 EC2. Contains no credentials.
set -euo pipefail
umask 027
# The application SG only allows egress TCP 443: apt must use HTTPS before anything else (no port 80).
install -d -m 0700 /var/lib/pedidos360-provision
cp -n /etc/apt/sources.list.d/ubuntu.sources /var/lib/pedidos360-provision/ubuntu.sources.orig 2>/dev/null || true
cat > /etc/apt/sources.list.d/ubuntu.sources <<'SOURCES'
Types: deb
URIs: https://archive.ubuntu.com/ubuntu
Suites: noble noble-updates noble-backports
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

Types: deb
URIs: https://security.ubuntu.com/ubuntu
Suites: noble-security
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
SOURCES
rm -f /etc/apt/sources.list.d/*.list /etc/apt/sources.list
[ ! -e /etc/apt/sources.list ] || : > /etc/apt/sources.list
export DEBIAN_FRONTEND=noninteractive
# Verify HTTPS apt before continuing; stop (no bootstrap-complete marker) if it cannot update.
ok=0
for attempt in 1 2 3 4 5; do
  log=/var/lib/pedidos360-provision/apt-update.log
  if apt-get -o Acquire::Retries=3 -o Acquire::https::Timeout=20 update > "$log" 2>&1 \
     && ! grep -qE '^(Err:|W: (Failed|Some index files failed))' "$log"; then ok=1; break; fi
  sleep $((attempt * 10))
done
[ "$ok" = 1 ] || { echo "apt-get update over HTTPS failed; see /var/lib/pedidos360-provision/apt-update.log" >&2; exit 1; }
grep -qE '^(Hit|Get):.*https://(archive|security)\.ubuntu\.com' /var/lib/pedidos360-provision/apt-update.log
touch /var/lib/pedidos360-provision/apt-https-ok
apt-get install -y --no-install-recommends ca-certificates curl unzip mysql-client
install -d -m 0755 /opt/pedidos360/releases /opt/pedidos360/runtime /etc/pedidos360/tls
archive=/var/lib/pedidos360-provision/temurin.tar.gz
curl --fail --location --retry 3 --proto '=https' --proto-redir '=https' \
  'https://github.com/adoptium/temurin25-binaries/releases/download/jdk-25.0.4.1%2B1/OpenJDK25U-jdk_x64_linux_hotspot_25.0.4.1_1.tar.gz' -o "$archive"
echo "dbb698396d478e7fa2b1e50f4103324b2a99b90569ee27c33f2261f9215cf41e  $archive" | sha256sum -c -
tar -xzf "$archive" -C /opt/pedidos360/runtime --strip-components=1
/opt/pedidos360/runtime/bin/java --version
for component in bff catalog orders; do
  id "pedidos360-$component" >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin "pedidos360-$component"
  install -d -m 0750 -o "pedidos360-$component" -g "pedidos360-$component" "/var/log/pedidos360/$component"
done
curl --fail --location --retry 3 --proto '=https' --proto-redir '=https' \
  'https://truststore.pki.rds.amazonaws.com/us-east-1/us-east-1-bundle.pem' -o /etc/pedidos360/tls/rds-ca-bundle.pem
chmod 0644 /etc/pedidos360/tls/rds-ca-bundle.pem
# The Ubuntu image normally includes SSM. This does not alter the lab IAM role.
if snap list amazon-ssm-agent >/dev/null 2>&1; then
  snap start amazon-ssm-agent
else
  curl --fail --location --retry 3 --proto '=https' --proto-redir '=https' \
    'https://s3.us-east-1.amazonaws.com/amazon-ssm-us-east-1/latest/debian_amd64/amazon-ssm-agent.deb' \
    -o /var/lib/pedidos360-provision/amazon-ssm-agent.deb
  dpkg -i /var/lib/pedidos360-provision/amazon-ssm-agent.deb
  systemctl enable --now amazon-ssm-agent
fi
touch /var/lib/pedidos360-provision/bootstrap-complete
