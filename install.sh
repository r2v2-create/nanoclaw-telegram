#!/usr/bin/env bash
# nanoclaw-telegram — one-shot installer
# Run as root on the target EC2 instance.
set -euo pipefail

INSTALL_DIR="/opt/nanoclaw-telegram"
CONFIG_DIR="/etc/nanoclaw"
SERVICE_NAME="nanoclaw-telegram"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== nanoclaw-telegram installer ==="

# 1. System deps
apt-get update -qq
apt-get install -y python3 python3-pip python3-venv --no-install-recommends

# 2. Install dir
mkdir -p "$INSTALL_DIR"
cp "$SCRIPT_DIR/telegram_bot.py" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/telegram_bot.py"

# 3. Python venv + deps
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet requests pyyaml boto3

# 4. Config
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/telegram-config.yml" ]; then
    cp "$SCRIPT_DIR/config.example.yml" "$CONFIG_DIR/telegram-config.yml"
    echo ""
    echo "⚠️  Config template installed to $CONFIG_DIR/telegram-config.yml"
    echo "    Edit it (or populate AWS Secrets Manager) before starting the service."
fi

# 5. systemd
cp "$SCRIPT_DIR/systemd/nanoclaw-telegram.service" "/etc/systemd/system/$SERVICE_NAME.service"

# Set correct user (ubuntu on EC2, or override via NANOCLAW_USER)
RUN_USER="${NANOCLAW_USER:-ubuntu}"
sed -i "s/^User=.*/User=$RUN_USER/" "/etc/systemd/system/$SERVICE_NAME.service"
sed -i "s/^Group=.*/Group=$RUN_USER/" "/etc/systemd/system/$SERVICE_NAME.service"
chown -R "$RUN_USER:$RUN_USER" "$INSTALL_DIR"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

echo ""
echo "✅ nanoclaw-telegram installed."
echo ""
echo "Next steps:"
echo "  1. Edit /etc/nanoclaw/telegram-config.yml  (or populate nanoclaw/telegram in Secrets Manager)"
echo "  2. systemctl start $SERVICE_NAME"
echo "  3. systemctl status $SERVICE_NAME"
echo "  4. journalctl -u $SERVICE_NAME -f"
