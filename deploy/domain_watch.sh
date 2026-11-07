#!/usr/bin/env bash
# Проверяет, заработал ли свой домен; если да — переключает бота на него и выключает проверку.
# Запускается таймером kurator-domain.timer (ставит install.sh, когда домен ещё не включился).
set -uo pipefail
APP=/opt/kurator
DOMAIN="${1:?домен}"
IP="$(curl -4 -fsS --max-time 8 https://api.ipify.org || true)"
[ -n "$IP" ] || exit 0
getent ahostsv4 "$DOMAIN" 2>/dev/null | awk '{print $1}' | grep -qx "$IP" || exit 0      # DNS ещё не обновился
systemctl reload caddy 2>/dev/null || true                                                  # пусть Caddy сразу попробует сертификат
if [ -f /etc/nginx/conf.d/kurator.conf ]; then
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email --redirect >/dev/null 2>&1 || exit 0
fi
for i in $(seq 1 12); do
  curl -fsS --max-time 10 "https://$DOMAIN/" -o /dev/null 2>/dev/null && break
  [ "$i" -eq 12 ] && exit 0                                                                  # сертификата ещё нет — попробуем позже
  sleep 10
done
if grep -q '^WEBAPP_URL=' "$APP/.env"; then sed -i "s|^WEBAPP_URL=.*|WEBAPP_URL=https://$DOMAIN|" "$APP/.env"
else echo "WEBAPP_URL=https://$DOMAIN" >> "$APP/.env"; fi
chown kurator:kurator "$APP/.env" && chmod 600 "$APP/.env"
systemctl restart kurator
systemctl disable --now kurator-domain.timer >/dev/null 2>&1 || true
# сообщим главному куратору
TOKEN="$(grep -E '^BOT_TOKEN=' "$APP/.env" | cut -d= -f2- | tr -d ' "')"
for id in $(grep -E '^CURATOR_IDS=' "$APP/.env" | cut -d= -f2- | tr -d ' "' | tr ',' ' '); do
  curl -fsS --max-time 10 "https://api.telegram.org/bot$TOKEN/sendMessage" \
    --data-urlencode "chat_id=$id" --data-urlencode "text=✅ Домен https://$DOMAIN заработал — бот переключился на него. Кнопка «Открыть» уже ведёт туда." >/dev/null || true
done
echo "переключено на https://$DOMAIN"
