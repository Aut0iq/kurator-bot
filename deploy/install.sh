#!/usr/bin/env bash
set -euo pipefail

APP=/opt/kurator
SVC=kurator
USER_NAME=kurator
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="${1:-}"

say()  { printf '\n\033[1;35m▶ %s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31m✗ %s\033[0m\n' "$*"; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Запустите от root: sudo bash deploy/install.sh"
[ -f "$SRC/bot/main.py" ] || die "Не нашёл bot/main.py — запускайте скрипт из папки проекта"

say "Устанавливаю системные пакеты"
if command -v apt-get >/dev/null; then
  PM=apt
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq python3 python3-venv python3-pip curl rsync ca-certificates gnupg debian-keyring debian-archive-keyring apt-transport-https >/dev/null 2>&1 \
    || apt-get install -y -qq python3 python3-venv python3-pip curl rsync ca-certificates gnupg >/dev/null
elif command -v dnf >/dev/null || command -v yum >/dev/null; then
  PM=dnf; command -v dnf >/dev/null || PM=yum
  $PM install -y -q python3 python3-pip curl rsync ca-certificates >/dev/null
else
  die "Не знаю менеджер пакетов этой системы. Нужны: python3 (3.10+), python3-venv, curl, rsync"
fi
ok "пакеты"

PY=python3
for v in python3.13 python3.12 python3.11 python3.10; do command -v $v >/dev/null && { PY=$v; break; }; done
$PY -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' \
  || die "Нужен Python 3.10 или новее (сейчас: $($PY --version)). Обновите систему, например до Ubuntu 22.04+ / Debian 12"
ok "$($PY --version)"

say "Копирую бота в $APP"
id "$USER_NAME" >/dev/null 2>&1 || useradd --system --home "$APP" --shell /usr/sbin/nologin "$USER_NAME"
mkdir -p "$APP/data" "$APP/backups"
rsync -a --delete --exclude '.venv' --exclude '__pycache__' --exclude 'data' --exclude 'backups' --exclude '.env' --exclude 'dist' --exclude 'android-keystore' --exclude 'android/app/build' --exclude 'android/.gradle' --exclude 'android/build' \
      "$SRC/" "$APP/"
if [ -f "$SRC/data/kurator.db" ] && [ ! -f "$APP/data/kurator.db" ]; then
  cp "$SRC/data/kurator.db" "$APP/data/kurator.db"
  for x in wal shm; do [ -f "$SRC/data/kurator.db-$x" ] && cp "$SRC/data/kurator.db-$x" "$APP/data/kurator.db-$x"; done
  ok "перенёс базу с компьютера (data/kurator.db)"
elif [ -f "$APP/data/kurator.db" ]; then
  ok "база на сервере уже есть — оставляю её"
fi

if [ ! -f "$APP/.env" ]; then
  if   [ -f "$SRC/.env" ];         then cp "$SRC/.env" "$APP/.env"
  elif [ -f "$SRC/.env.example" ]; then cp "$SRC/.env.example" "$APP/.env"
  else die "Нет .env / .env.example"; fi
fi
if ! grep -Eq '^BOT_TOKEN=' "$APP/.env"; then echo 'BOT_TOKEN=' >> "$APP/.env"; fi
if ! grep -Eq '^BOT_TOKEN=[0-9]+:' "$APP/.env"; then
  warn "BOT_TOKEN пустой — Telegram-уведомления отключены, вход в приложение по логину/паролю"
fi

IP="$(curl -4 -fsS --max-time 8 https://api.ipify.org || curl -4 -fsS --max-time 8 https://ifconfig.me || true)"
SSLIP=""; [ -n "$IP" ] && SSLIP="bot.${IP}.sslip.io"
if [ -z "$DOMAIN" ]; then
  [ -n "$SSLIP" ] || die "Не смог узнать внешний IP. Укажите адрес явно: sudo bash deploy/install.sh 1.2.3.4.sslip.io"
  DOMAIN="$SSLIP"
fi
HOSTS="$DOMAIN"
[ -n "$SSLIP" ] && [ "$SSLIP" != "$DOMAIN" ] && HOSTS="$DOMAIN, $SSLIP"
URL="https://$DOMAIN"
PENDING=""
if [ "$DOMAIN" != "$SSLIP" ] && [ -n "$SSLIP" ]; then
  if ! getent ahostsv4 "$DOMAIN" 2>/dev/null | awk '{print $1}' | grep -qx "$IP"; then
    URL="https://$SSLIP"; PENDING=1
    warn "домен $DOMAIN пока не указывает на $IP — временно работаю на $URL"
    warn "как только домен заработает, бот сам переключится на https://$DOMAIN (проверка каждые 5 минут)"
  fi
fi
ok "адрес Mini App: $URL"

PORT=8080
while ss -ltn 2>/dev/null | grep -q ":$PORT " && ! systemctl is-active -q $SVC 2>/dev/null; do PORT=$((PORT+1)); done

setenv() {
  if grep -q "^$1=" "$APP/.env"; then sed -i "s|^$1=.*|$1=$2|" "$APP/.env"; else echo "$1=$2" >> "$APP/.env"; fi
}
setenv WEBAPP_URL "$URL"
for k in OPERATOR_NAME OPERATOR_INFO OPERATOR_CONTACT SERVER_LOCATION; do
  for f in "$SRC/.env" "$SRC/.env.example"; do
    v="$(grep -E "^$k=" "$f" 2>/dev/null | head -1 | cut -d= -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//;s/[|&]//g' || true)"
    if [ -n "$v" ]; then setenv "$k" "$v"; break; fi
  done
done
setenv HOST 127.0.0.1
setenv PORT "$PORT"
setenv DB_PATH data/kurator.db
grep -q '^CURATOR_IDS=' "$APP/.env" || echo 'CURATOR_IDS=' >> "$APP/.env"
chmod 600 "$APP/.env"
ok ".env настроен (порт $PORT)"

say "Ставлю зависимости Python"
[ -d "$APP/.venv" ] || $PY -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install -q --upgrade pip >/dev/null
"$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt"
chown -R "$USER_NAME:$USER_NAME" "$APP"
ok "зависимости"

say "Создаю сервис $SVC"
cat > /etc/systemd/system/$SVC.service <<UNIT
[Unit]
Description=Куратор + (Telegram-бот + Mini App)
After=network-online.target
Wants=network-online.target

[Service]
User=$USER_NAME
WorkingDirectory=$APP
ExecStart=$APP/.venv/bin/python bot/main.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
NoNewPrivileges=true
ProtectSystem=full
ReadWritePaths=$APP/data $APP/backups

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/$SVC-backup.service <<UNIT
[Unit]
Description=Резервная копия базы «Куратор +»
[Service]
Type=oneshot
User=$USER_NAME
WorkingDirectory=$APP
ExecStart=/bin/bash $APP/deploy/backup.sh
UNIT
cat > /etc/systemd/system/$SVC-backup.timer <<UNIT
[Unit]
Description=Каждый день в 03:30 — резервная копия базы
[Timer]
OnCalendar=*-*-* 03:30:00
Persistent=true
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable -q --now $SVC-backup.timer
ok "резервная копия каждую ночь (хранятся 14 дней, присылаются главному куратору)"

say "Настраиваю HTTPS для $DOMAIN"
WEB_BUSY="$(ss -ltnp 2>/dev/null | grep -E ':(80|443) ' | grep -oE '"[a-z0-9_-]+"' | tr -d '"' | sort -u | tr '\n' ' ' || true)"
if echo "$WEB_BUSY" | grep -qw nginx; then
  warn "порты 80/443 заняты nginx — настраиваю через него"
  if [ "$PM" = apt ]; then apt-get install -y -qq certbot python3-certbot-nginx >/dev/null; else $PM install -y -q certbot python3-certbot-nginx >/dev/null; fi
  CONF=/etc/nginx/conf.d/kurator.conf
  cat > $CONF <<NGX
server {
    listen 80;
    server_name ${HOSTS//,/};
    client_max_body_size 5m;
    location / {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
NGX
  nginx -t >/dev/null && systemctl reload nginx
  certbot --nginx -d "${URL#https://}" --non-interactive --agree-tos --register-unsafely-without-email --redirect >/dev/null \
    && ok "сертификат Let's Encrypt получен" || warn "certbot не смог получить сертификат — проверьте, что порт 80 открыт снаружи"
elif [ -n "$WEB_BUSY" ] && ! echo "$WEB_BUSY" | grep -qw caddy; then
  warn "порты 80/443 заняты: $WEB_BUSY"
  warn "Настройте в нём проксирование https://$DOMAIN → http://127.0.0.1:$PORT и перезапустите бота: systemctl restart $SVC"
else
  if ! command -v caddy >/dev/null; then
    if [ "$PM" = apt ]; then
      curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
      curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt > /etc/apt/sources.list.d/caddy-stable.list
      apt-get update -qq && apt-get install -y -qq caddy >/dev/null
    else
      $PM install -y -q 'dnf-command(copr)' >/dev/null 2>&1 || true
      $PM copr enable -y @caddy/caddy >/dev/null 2>&1 && $PM install -y -q caddy >/dev/null || true
    fi
  fi
  if ! command -v caddy >/dev/null; then
    ARCH=amd64; [ "$(uname -m)" = aarch64 ] && ARCH=arm64
    curl -fsSL "https://caddyserver.com/api/download?os=linux&arch=$ARCH" -o /usr/local/bin/caddy && chmod +x /usr/local/bin/caddy
    id caddy >/dev/null 2>&1 || useradd --system --home /var/lib/caddy --create-home --shell /usr/sbin/nologin caddy
    mkdir -p /etc/caddy && touch /etc/caddy/Caddyfile
    cat > /etc/systemd/system/caddy.service <<UNIT
[Unit]
Description=Caddy
After=network-online.target
[Service]
User=caddy
ExecStart=/usr/local/bin/caddy run --environ --config /etc/caddy/Caddyfile
ExecReload=/usr/local/bin/caddy reload --config /etc/caddy/Caddyfile --force
AmbientCapabilities=CAP_NET_BIND_SERVICE
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT
    systemctl daemon-reload
  fi
  CF=/etc/caddy/Caddyfile
  mkdir -p /etc/caddy
  touch $CF
  sed -i '/# kurator-bot begin/,/# kurator-bot end/d' $CF
  if grep -q '^:80' $CF && grep -q 'file_server' $CF && [ "$(grep -v '^[[:space:]]*#' $CF | grep -c .)" -lt 8 ]; then : > $CF; fi
  cat >> $CF <<CADDY
$HOSTS {
    encode gzip
    reverse_proxy 127.0.0.1:$PORT
}
CADDY
  case "$DOMAIN" in
    *.sslip.io|*.*.*) ;;
    *) sed -i '/# kurator-bot end/i www.'"$DOMAIN"' {\n    redir https://'"$DOMAIN"'{uri} permanent\n}' $CF ;;
  esac
  systemctl enable -q caddy
  systemctl restart caddy
  ok "Caddy сам получит и будет продлевать HTTPS-сертификат"
fi

if command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
  ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; ok "ufw: открыл 80 и 443"
fi
if systemctl is-active -q firewalld 2>/dev/null; then
  firewall-cmd -q --permanent --add-service=http --add-service=https && firewall-cmd -q --reload; ok "firewalld: открыл http и https"
fi

if [ -n "$PENDING" ]; then
  cat > /etc/systemd/system/$SVC-domain.service <<UNIT
[Unit]
Description=Переключение «Куратор +» на домен $DOMAIN
[Service]
Type=oneshot
ExecStart=/bin/bash $APP/deploy/domain_watch.sh $DOMAIN
UNIT
  cat > /etc/systemd/system/$SVC-domain.timer <<UNIT
[Unit]
Description=Каждые 5 минут: заработал ли домен $DOMAIN
[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
[Install]
WantedBy=timers.target
UNIT
  systemctl daemon-reload
  systemctl enable -q --now $SVC-domain.timer
  ok "жду домен $DOMAIN — переключусь сам"
else
  systemctl disable -q --now $SVC-domain.timer 2>/dev/null || true
fi

say "Запускаю бота"
systemctl enable -q $SVC
systemctl restart $SVC
sleep 4
if systemctl is-active -q $SVC; then
  ok "бот работает"
else
  journalctl -u $SVC -n 30 --no-pager || true
  die "Бот не запустился — выше лог. Частая причина: бот ещё запущен на компьютере (ошибка Conflict)."
fi

for i in 1 2 3 4 5 6; do
  if curl -fsS --max-time 10 "$URL/" -o /dev/null 2>/dev/null; then ok "Mini App открывается: $URL"; break; fi
  [ $i -eq 6 ] && warn "$URL пока не отвечает — сертификат может выпускаться ещё 1–2 минуты. Проверьте: journalctl -u caddy -n 50"
  sleep 10
done

cat <<DONE

✅ Готово!
  Mini App:     $URL
  Логи бота:    journalctl -u $SVC -f
  Перезапуск:   systemctl restart $SVC
  Настройки:    $APP/.env
  База:         $APP/data/kurator.db   (копии — $APP/backups)
  Обновление:   загрузите новую версию папки и выполните  sudo bash deploy/update.sh

Не забудьте остановить бота на компьютере — два бота с одним токеном мешают друг другу.
DONE
