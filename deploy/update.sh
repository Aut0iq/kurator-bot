#!/usr/bin/env bash
set -euo pipefail
APP=/opt/kurator
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ "$(id -u)" -eq 0 ] || { echo "Запустите через sudo"; exit 1; }
[ -d "$APP" ] || { echo "Бот ещё не установлен — сначала sudo bash deploy/install.sh"; exit 1; }
if [ "$SRC" != "$APP" ]; then
  rsync -a --delete --exclude '.venv' --exclude '__pycache__' --exclude 'data' --exclude 'backups' --exclude '.env' --exclude 'dist' --exclude 'android-keystore' --exclude 'android/app/build' --exclude 'android/.gradle' --exclude 'android/build' "$SRC/" "$APP/"
fi
bash "$APP/deploy/backup.sh" --quiet || true
"$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt"
chown -R kurator:kurator "$APP"
systemctl restart kurator
sleep 3
systemctl is-active -q kurator && echo "✓ Обновлено и перезапущено" || { journalctl -u kurator -n 30 --no-pager; exit 1; }
