#!/usr/bin/env bash
set -euo pipefail

DATE=$(date +%F-%H%M%S)
BACKUP_DIR="/root/vpn-bot/backups/$DATE"

mkdir -p "$BACKUP_DIR"

# DB dump
sudo -u postgres pg_dump vpnbot > "$BACKUP_DIR/vpnbot.sql"

# env
cp /root/vpn-bot/.env "$BACKUP_DIR/.env"

# configs
tar -czf "$BACKUP_DIR/configs.tar.gz" /root/vpn-bot/configs

echo "Backup created: $BACKUP_DIR"
