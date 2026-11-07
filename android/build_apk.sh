#!/usr/bin/env bash
# Сборка Android-приложения прямо на сервере. Результат — /opt/kurator/dist/kurator.apk,
# его раздаёт бот по адресу https://<ваш адрес>/app.apk (команда /app).
#   sudo bash /opt/kurator/android/build_apk.sh
# Первый раз качает Android SDK (~600 МБ) и собирает 5–10 минут; повторно — 1–2 минуты.
set -euo pipefail

APP=/opt/kurator
SDK=/opt/android-sdk
KS_DIR=$APP/android-keystore
say()  { printf '\n\033[1;35m▶ %s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31m✗ %s\033[0m\n' "$*"; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Запустите от root: sudo bash $APP/android/build_apk.sh"
[ -f "$APP/android/app/build.gradle" ] || die "Нет $APP/android — обновите бота через upload.bat"
URL="$(grep -E '^WEBAPP_URL=' "$APP/.env" | cut -d= -f2- | tr -d ' "')"
[[ "$URL" == https://* ]] || die "В $APP/.env нет WEBAPP_URL с https — сначала установите бота (deploy/install.sh)"

# ---------- Java 17
say "Java"
if ! command -v javac >/dev/null || ! javac -version 2>&1 | grep -qE 'javac (1[7-9]|2[0-9])'; then
  if command -v apt-get >/dev/null; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq && apt-get install -y -qq openjdk-17-jdk-headless unzip >/dev/null
  else
    (command -v dnf >/dev/null && dnf install -y -q java-17-openjdk-devel unzip) || yum install -y -q java-17-openjdk-devel unzip
  fi
fi
command -v unzip >/dev/null || { command -v apt-get >/dev/null && apt-get install -y -qq unzip >/dev/null; }
ok "$(javac -version 2>&1)"

# ---------- Android SDK
say "Android SDK"
export ANDROID_HOME=$SDK ANDROID_SDK_ROOT=$SDK
if [ ! -x "$SDK/cmdline-tools/latest/bin/sdkmanager" ]; then
  mkdir -p "$SDK/cmdline-tools"
  TMP="$(mktemp -d)"
  curl -fsSL https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip -o "$TMP/tools.zip"
  unzip -q "$TMP/tools.zip" -d "$TMP"
  rm -rf "$SDK/cmdline-tools/latest" && mv "$TMP/cmdline-tools" "$SDK/cmdline-tools/latest"
  rm -rf "$TMP"
fi
SDKM="$SDK/cmdline-tools/latest/bin/sdkmanager"
yes | "$SDKM" --sdk_root="$SDK" --licenses >/dev/null 2>&1 || true
"$SDKM" --sdk_root="$SDK" --install "platforms;android-34" "build-tools;34.0.0" >/dev/null
ok "SDK готов ($SDK)"

# ---------- память: Gradle нужно ~1.5 ГБ
MEM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
SWAP_MB=$(awk '/SwapTotal/ {print int($2/1024)}' /proc/meminfo)
if [ $((MEM_MB + SWAP_MB)) -lt 2600 ] && [ ! -f /swapfile-kurator ]; then
  say "Мало памяти (${MEM_MB} МБ) — добавляю файл подкачки 2 ГБ"
  (fallocate -l 2G /swapfile-kurator || dd if=/dev/zero of=/swapfile-kurator bs=1M count=2048 status=none)
  chmod 600 /swapfile-kurator && mkswap /swapfile-kurator >/dev/null && swapon /swapfile-kurator
  grep -q swapfile-kurator /etc/fstab || echo '/swapfile-kurator none swap sw 0 0' >> /etc/fstab
  ok "подкачка включена"
fi

# ---------- ключ подписи (один на все версии — иначе обновление не встанет поверх)
say "Ключ подписи"
mkdir -p "$KS_DIR" && chmod 700 "$KS_DIR"
if [ ! -f "$KS_DIR/kurator.jks" ] && [ -f "$APP/android/keystore/kurator.jks" ]; then
  cp "$APP/android/keystore/kurator.jks" "$APP/android/keystore/pass" "$KS_DIR/" && chmod 600 "$KS_DIR/pass"
  ok "использую ключ из android/keystore (тот же, что у готового kurator.apk)"
fi
if [ ! -f "$KS_DIR/kurator.jks" ]; then
  PASS="$(head -c 18 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 20)"
  echo "$PASS" > "$KS_DIR/pass" && chmod 600 "$KS_DIR/pass"
  keytool -genkeypair -keystore "$KS_DIR/kurator.jks" -alias kurator -keyalg RSA -keysize 2048 -validity 36500 \
          -storepass "$PASS" -keypass "$PASS" -dname "CN=Pomoshnik Starosty, O=Kurator, C=RU" >/dev/null 2>&1
  ok "создан новый ключ $KS_DIR/kurator.jks — не удаляйте его (лежит и в резервной копии)"
else
  ok "используется существующий ключ"
fi
PASS="$(cat "$KS_DIR/pass")"

# ---------- сборка
say "Собираю приложение для $URL"
cd "$APP/android"
chmod +x gradlew
VCODE=$(( $(date +%s) / 60 - 29000000 ))          # растёт с каждой сборкой
VNAME="1.$(date +%y%m%d.%H%M)"
./gradlew --no-daemon -q assembleRelease \
  -PserverUrl="$URL" -PversionCode="$VCODE" -PversionName="$VNAME" \
  -Pkeystore="$KS_DIR/kurator.jks" -PstorePass="$PASS"
APK="$APP/android/app/build/outputs/apk/release/app-release.apk"
[ -f "$APK" ] || die "Сборка не создала APK — смотрите сообщения выше"
mkdir -p "$APP/dist"
cp "$APK" "$APP/dist/kurator.apk"
# сведения о версии: бот по ним предложит обновиться, а старые версии попросит обновить (min_code)
NOTES="$(python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1])).get("notes", []), ensure_ascii=False))' "$APP/android/kurator.json" 2>/dev/null || echo '[]')"
cat > "$APP/dist/kurator.json" <<JSON
{"version_code": $VCODE, "version_name": "$VNAME", "min_code": ${MIN_CODE:-$VCODE}, "notes": $NOTES}
JSON
cp "$KS_DIR/kurator.jks" "$APP/backups/android-keystore.jks" 2>/dev/null || true
cp "$KS_DIR/pass" "$APP/backups/android-keystore.pass" 2>/dev/null || true
chown -R kurator:kurator "$APP/dist" "$APP/backups" 2>/dev/null || true
SIZE=$(du -h "$APP/dist/kurator.apk" | cut -f1)

cat <<DONE

✅ Приложение собрано: версия $VNAME, $SIZE
  Скачать на телефон:  $URL/app.apk
  В боте:              команда /app (ссылка появится сама)
  В Mini App:          Ещё → «Приложение для Android»
DONE
