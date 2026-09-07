#!/usr/bin/env bash
set -euo pipefail

# Installs the non-container observability stack on Ubuntu 24.04.
if [[ ${EUID} -ne 0 ]]; then
  echo 'Run as root: sudo env GRAFANA_ADMIN_PASSWORD=... bash scripts/observability-install.sh' >&2
  exit 1
fi

: "${GRAFANA_ADMIN_PASSWORD:?Set GRAFANA_ADMIN_PASSWORD before installation}"
if [[ "$GRAFANA_ADMIN_PASSWORD" == 'replace-with-a-strong-password' ]]; then
  echo 'Set a real GRAFANA_ADMIN_PASSWORD; do not use the example value.' >&2
  exit 1
fi
if [[ "$GRAFANA_ADMIN_PASSWORD" == *$'\n'* || "$GRAFANA_ADMIN_USER" == *$'\n'* ]]; then
  echo 'Grafana administrator values must not contain a newline.' >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOKI_VERSION=${LOKI_VERSION:-3.0.0}
PROMETHEUS_VERSION=${PROMETHEUS_VERSION:-2.53.1}
GRAFANA_ADMIN_USER=${GRAFANA_ADMIN_USER:-admin}
ARCH=$(dpkg --print-architecture)

if [[ "$ARCH" != 'amd64' ]]; then
  echo "Unsupported architecture: ${ARCH}. Add an explicit arm64 release path before installing." >&2
  exit 1
fi

apt-get update
apt-get install -y ca-certificates curl gpg tar unzip

install -d -m 0755 /etc/apt/keyrings
curl --fail --location --proto '=https' --tlsv1.2 https://apt.grafana.com/gpg.key \
  | gpg --dearmor --yes -o /etc/apt/keyrings/grafana.gpg
printf '%s\n' 'deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main' \
  > /etc/apt/sources.list.d/grafana.list
apt-get update
apt-get install -y grafana

work_dir=$(mktemp -d)
trap 'rm -rf "$work_dir"' EXIT

curl --fail --location --proto '=https' --tlsv1.2 \
  -o "$work_dir/loki.zip" \
  "https://github.com/grafana/loki/releases/download/v${LOKI_VERSION}/loki-linux-amd64.zip"
unzip -q "$work_dir/loki.zip" -d "$work_dir/loki"
install -m 0755 "$work_dir/loki/loki-linux-amd64" /usr/local/bin/loki

curl --fail --location --proto '=https' --tlsv1.2 \
  -o "$work_dir/prometheus.tar.gz" \
  "https://github.com/prometheus/prometheus/releases/download/v${PROMETHEUS_VERSION}/prometheus-${PROMETHEUS_VERSION}.linux-amd64.tar.gz"
tar -xzf "$work_dir/prometheus.tar.gz" -C "$work_dir"
install -m 0755 "$work_dir/prometheus-${PROMETHEUS_VERSION}.linux-amd64/prometheus" /usr/local/bin/prometheus

getent group loki >/dev/null || groupadd --system loki
getent passwd loki >/dev/null || useradd --system --home /var/lib/loki --shell /usr/sbin/nologin --gid loki loki
getent group prometheus >/dev/null || groupadd --system prometheus
getent passwd prometheus >/dev/null || useradd --system --home /var/lib/prometheus --shell /usr/sbin/nologin --gid prometheus prometheus

install -d -o loki -g loki -m 0750 /var/lib/loki /var/lib/loki/chunks /var/lib/loki/compactor
install -d -o prometheus -g prometheus -m 0750 /var/lib/prometheus
install -d -m 0755 /etc/loki /etc/prometheus /etc/grafana/provisioning/datasources
install -m 0644 "$ROOT_DIR/observability/loki/config.yml" /etc/loki/config.yml
install -m 0644 "$ROOT_DIR/observability/prometheus/prometheus.yml" /etc/prometheus/prometheus.yml
install -m 0644 "$ROOT_DIR/observability/grafana/provisioning/datasources/datasources.yml" \
  /etc/grafana/provisioning/datasources/luck-observability.yml
install -m 0644 "$ROOT_DIR/observability/systemd/loki.service" /etc/systemd/system/loki.service
install -m 0644 "$ROOT_DIR/observability/systemd/prometheus.service" /etc/systemd/system/prometheus.service

install -d -m 0755 /etc/systemd/system/grafana-server.service.d
{
  printf '%s\n' 'GF_SERVER_HTTP_ADDR=127.0.0.1'
  printf '%s\n' 'GF_SERVER_HTTP_PORT=3000'
  printf '%s\n' 'GF_SERVER_ROOT_URL=http://127.0.0.1:3000'
  printf 'GF_SECURITY_ADMIN_USER=%q\n' "$GRAFANA_ADMIN_USER"
  printf 'GF_SECURITY_ADMIN_PASSWORD=%q\n' "$GRAFANA_ADMIN_PASSWORD"
  printf '%s\n' 'GF_USERS_ALLOW_SIGN_UP=false'
  printf '%s\n' 'GF_AUTH_ANONYMOUS_ENABLED=false'
} > /etc/luck-observability.env
chmod 0600 /etc/luck-observability.env
cat > /etc/systemd/system/grafana-server.service.d/luck-observability.conf <<'EOF'
[Service]
EnvironmentFile=/etc/luck-observability.env
EOF

systemctl daemon-reload
systemctl enable --now loki prometheus grafana-server
"$ROOT_DIR/scripts/observability-test.sh"
