#!/usr/bin/env bash
# Резервная копия базы: сохраняет в backups/ (14 последних) и присылает главным кураторам в Telegram.
# Вручную:  sudo -u kurator bash /opt/kurator/deploy/backup.sh
set -euo pipefail
APP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QUIET="${1:-}"
cd "$APP"
DB="data/kurator.db"
[ -f "$DB" ] || { echo "База ещё не создана"; exit 0; }
mkdir -p backups
OUT="backups/kurator-$(date +%Y%m%d-%H%M).db"
"$APP/.venv/bin/python" - "$DB" "$OUT" <<'PY'
import sqlite3, sys
src, dst = sqlite3.connect(sys.argv[1]), sqlite3.connect(sys.argv[2])
src.backup(dst); dst.close(); src.close()
PY
ls -1t backups/kurator-*.db | tail -n +15 | xargs -r rm -f
echo "✓ $OUT"
if [ "$QUIET" = "--quiet" ]; then exit 0; fi
TOKEN="$( (grep -E '^BOT_TOKEN=' .env || true) | cut -d= -f2- | tr -d ' "')"
IDS="$( (grep -E '^CURATOR_IDS=' .env || true) | cut -d= -f2- | tr -d ' "')"
[ -n "$TOKEN" ] && [ -n "$IDS" ] || exit 0
for id in ${IDS//,/ }; do
  curl -fsS -o /dev/null -F chat_id="$id" -F document=@"$OUT" \
       -F caption="🗄 Резервная копия базы «Куратор +» · $(date '+%d.%m.%Y %H:%M')" \
       "https://api.telegram.org/bot$TOKEN/sendDocument" || echo "не удалось отправить копию $id"
done
