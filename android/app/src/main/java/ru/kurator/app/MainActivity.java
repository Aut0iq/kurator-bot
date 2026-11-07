package ru.kurator.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.res.Configuration;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.provider.Settings;
import android.text.InputType;
import android.view.View;
import android.view.Window;
import android.util.Base64;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.HashMap;
import java.util.Map;

/**
 * «Куратор +» для Android — оболочка над веб-приложением бота.
 *
 * Всё содержимое (журнал, оценки, расписание…) приходит с вашего сервера, поэтому
 * приложение не нужно пересобирать при обновлении бота. Вход — через подтверждение в Telegram.
 * Адрес сервера вшивается при сборке (-PserverUrl=…) или вводится при первом запуске.
 */
public class MainActivity extends Activity {

    private static final String PREFS = "kurator";
    private static final int FILE_REQUEST = 42;

    private WebView web;
    private SharedPreferences prefs;
    private String server = "";
    private String primary = "";      // основной адрес (свой домен)
    private String alt = "";          // запасной адрес (бот на компьютере через ngrok)
    private boolean triedAlt;
    private ValueCallback<Uri[]> fileCallback;
    private boolean darkPage;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        CrashLog.install(this);
        darkPage = isSystemDark();
        paintBars();

        // отладка WebView — только в отладочной сборке
        if ((getApplicationInfo().flags & android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0) WebView.setWebContentsDebuggingEnabled(true);
        web = new WebView(this);
        web.setBackgroundColor(darkPage ? Color.parseColor("#0B0C10") : Color.parseColor("#F2F3F7"));
        FrameLayout root = new FrameLayout(this);
        root.addView(web, new FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));
        setContentView(root);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        // Свой User-Agent (без «Mozilla»): ngrok и подобные туннели не показывают приложению страницу-предупреждение
        // сервер по коду версии понимает, старое приложение или новое (старым показывает «Обновите приложение»)
        s.setUserAgentString("KuratorApp/" + versionName() + " (code " + versionCode() + "; Android " + Build.VERSION.RELEASE + ")");
        s.setCacheMode(WebSettings.LOAD_DEFAULT);

        web.addJavascriptInterface(new Bridge(), "KuratorApp");
        web.setWebViewClient(new Client());
        web.setWebChromeClient(new Chrome());
        web.setDownloadListener((url, userAgent, contentDisposition, mimetype, contentLength) -> openExternal(url));

        String built = normalize(getString(R.string.server_url));
        server = normalize(prefs.getString("server", built));
        if (!built.isEmpty() && !built.equals(prefs.getString("built", ""))) {
            // новая сборка с другим адресом — переключаемся на него автоматически
            server = built;
            prefs.edit().putString("server", built).putString("built", built).apply();
        }
        primary = server;
        alt = normalize(getString(R.string.server_alt));
        if (savedInstanceState != null) {
            web.restoreState(savedInstanceState);
        } else if (server.isEmpty()) {
            askServer(null);
        } else {
            loadApp(getIntent());
        }
        if (Push.enabled(this)) Push.schedule(this);   // внутри — защищено от ошибок
    }

    /** Нажали на уведомление, когда приложение уже открыто, — переходим в нужный раздел. */
    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        String hash = intent == null ? null : intent.getStringExtra("hash");
        if (hash != null && web != null && !server.isEmpty()) {
            if (hash.isEmpty()) web.evaluateJavascript("window.boot && boot(true)", null);
            else web.evaluateJavascript("(function(){try{closeAllSheets();go('home','" + hash.replaceAll("[^a-z]", "") + "')}catch(e){location.hash='" + hash.replaceAll("[^a-z]", "") + "';location.reload()}})()", null);
        }
    }

    private void loadApp(Intent intent) {
        String hash = intent == null ? null : intent.getStringExtra("hash");
        if (hash != null && !hash.isEmpty() && !server.isEmpty()) {
            Map<String, String> h = new HashMap<>();
            h.put("ngrok-skip-browser-warning", "1");
            web.loadUrl(server + "/#" + hash.replaceAll("[^a-z]", ""), h);
        } else loadApp();
    }

    // ---------- загрузка
    /** Основной адрес не ответил — один раз пробуем запасной. */
    private boolean tryAlt() {
        if (triedAlt || alt.isEmpty() || alt.equals(server)) return false;
        triedAlt = true;
        server = alt;
        loadApp();
        return true;
    }

    private void loadApp() {
        if (server.isEmpty()) {
            askServer(null);
            return;
        }
        Map<String, String> h = new HashMap<>();
        h.put("ngrok-skip-browser-warning", "1");
        web.loadUrl(server + "/", h);
    }

    private void askServer(String error) {
        final EditText input = new EditText(this);
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        input.setHint("https://kyratorvsk.ru");
        input.setSingleLine(true);
        input.setText(server);
        int pad = (int) (20 * getResources().getDisplayMetrics().density);
        FrameLayout box = new FrameLayout(this);
        box.setPadding(pad, pad / 2, pad, 0);
        box.addView(input);

        String msg = "Адрес, по которому работает бот (WEBAPP_URL из .env) — его показывает команда /app в боте. Например https://kyratorvsk.ru";
        if (error != null) msg = error + "\n\n" + msg;
        new AlertDialog.Builder(this)
                .setTitle("Адрес сервера")
                .setMessage(msg)
                .setView(box)
                .setCancelable(false)
                .setPositiveButton("Подключиться", (d, w) -> {
                    String value = normalize(input.getText().toString());
                    if (value.isEmpty()) {
                        askServer("Введите адрес.");
                        return;
                    }
                    server = value;
                    primary = value;
                    triedAlt = false;
                    prefs.edit().putString("server", server).apply();
                    loadApp();
                })
                .setNegativeButton("Выход", (d, w) -> finish())
                .show();
    }

    private static String normalize(String url) {
        if (url == null) return "";
        String u = url.trim();
        if (u.isEmpty()) return "";
        if (!u.startsWith("http://") && !u.startsWith("https://")) u = "https://" + u;
        while (u.endsWith("/")) u = u.substring(0, u.length() - 1);
        return u;
    }

    private boolean isInternal(Uri uri) {
        if (uri == null || server.isEmpty()) return false;
        String scheme = uri.getScheme();
        if (!"https".equals(scheme) && !"http".equals(scheme)) return false;
        Uri base = Uri.parse(server);
        String host = uri.getHost();
        if (host == null || !host.equalsIgnoreCase(base.getHost())) return false;
        String path = uri.getPath();
        return path == null || !path.endsWith(".apk");      // файл приложения скачиваем браузером
    }

    void openExternal(String url) {
        if (url == null || url.isEmpty()) return;
        try {
            Intent i = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(i);
        } catch (ActivityNotFoundException e) {
            if (url.startsWith("tg://resolve?domain=")) {
                // Telegram не установлен — откроем t.me в браузере
                String rest = url.substring("tg://resolve?domain=".length()).replace("&start=", "?start=");
                openExternal("https://t.me/" + rest);
            } else {
                Toast.makeText(this, "Нет приложения, чтобы открыть ссылку", Toast.LENGTH_SHORT).show();
            }
        }
    }

    // ---------- обновление приложения
    private long versionCode() {
        try {
            android.content.pm.PackageInfo pi = getPackageManager().getPackageInfo(getPackageName(), 0);
            return Build.VERSION.SDK_INT >= 28 ? pi.getLongVersionCode() : pi.versionCode;
        } catch (Exception e) {
            return 0;
        }
    }

    // ---------- оформление
    private boolean isSystemDark() {
        int mode = getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK;
        return mode == Configuration.UI_MODE_NIGHT_YES;
    }

    @SuppressWarnings("deprecation")
    private void paintBars() {
        Window w = getWindow();
        int color = darkPage ? Color.parseColor("#0B0C10") : Color.parseColor("#F2F3F7");
        w.setStatusBarColor(color);
        w.setNavigationBarColor(color);
        View decor = w.getDecorView();
        int flags = decor.getSystemUiVisibility();
        if (darkPage) {
            flags &= ~View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
            flags &= ~View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
        } else {
            flags |= View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
            flags |= View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
        }
        decor.setSystemUiVisibility(flags);
    }

    private String versionName() {
        try {
            return getPackageManager().getPackageInfo(getPackageName(), 0).versionName;
        } catch (Exception e) {
            return "1.0";
        }
    }

    // ---------- жизненный цикл
    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (web == null) {
            super.onBackPressed();
            return;
        }
        web.evaluateJavascript("(window.__appBack && window.__appBack()) ? '1' : '0'", value -> {
            if ("\"1\"".equals(value)) return;
            if (web.canGoBack()) web.goBack();
            else finish();
        });
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (web != null) web.onResume();
    }

    @Override
    protected void onPause() {
        if (web != null) web.onPause();
        super.onPause();
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        if (web != null) web.saveState(outState);
    }

    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        super.onConfigurationChanged(newConfig);
        boolean dark = isSystemDark();
        if (dark != darkPage) {
            darkPage = dark;
            paintBars();
            if (web != null) web.reload();                    // страница перерисуется в новой теме
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == FILE_REQUEST && fileCallback != null) {
            fileCallback.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultCode, data));
            fileCallback = null;
        }
    }

    @Override
    protected void onDestroy() {
        if (web != null) {
            web.destroy();
            web = null;
        }
        super.onDestroy();
    }

    // ---------- WebView
    private class Client extends WebViewClient {
        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            Uri uri = request.getUrl();
            if (isInternal(uri)) return false;
            if ("file".equals(uri.getScheme())) return false;   // страница «нет связи»
            openExternal(uri.toString());
            return true;
        }

        @Override
        public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
            if (request.isForMainFrame() && !tryAlt()) {
                view.loadUrl("file:///android_asset/offline.html");
            }
        }

        @Override
        public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse response) {
            // бот выключен / туннель ngrok не запущен — вместо чужой страницы ошибки показываем свою
            if (request.isForMainFrame() && response.getStatusCode() >= 400 && !tryAlt()) {
                view.loadUrl("file:///android_asset/offline.html");
            }
        }
    }

    private class Chrome extends WebChromeClient {
        @Override
        public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
            if (fileCallback != null) fileCallback.onReceiveValue(null);
            fileCallback = callback;
            try {
                startActivityForResult(params.createIntent(), FILE_REQUEST);
                return true;
            } catch (ActivityNotFoundException e) {
                fileCallback = null;
                return false;
            }
        }
    }

    /** Методы, которые вызывает веб-приложение: window.KuratorApp.* (см. webapp/app.js). */
    private class Bridge {
        @JavascriptInterface
        public String getToken() {
            String t = prefs.getString("token", "");
            return t.isEmpty() ? prefs.getString("token:" + server, "") : t;
        }

        @JavascriptInterface
        public void setToken(String token) {
            prefs.edit().putString("token", token == null ? "" : token).remove("feed_since").apply();
            if (token == null || token.isEmpty()) Push.stop(MainActivity.this);     // вышли из аккаунта — уведомления не нужны
        }

        @JavascriptInterface
        public String serverUrl() {
            return server;
        }

        @JavascriptInterface
        public String version() {
            return versionName();
        }

        @JavascriptInterface
        public long versionCode() {
            return MainActivity.this.versionCode();
        }

        @JavascriptInterface
        public void vibrate(int ms) {
            Vibrator v = (Vibrator) getSystemService(Context.VIBRATOR_SERVICE);
            if (v == null || !v.hasVibrator()) return;
            int len = Math.max(1, Math.min(ms, 200));
            v.vibrate(VibrationEffect.createOneShot(len, VibrationEffect.DEFAULT_AMPLITUDE));
        }

        @JavascriptInterface
        public void openExternal(String url) {
            runOnUiThread(() -> MainActivity.this.openExternal(url));
        }

        @JavascriptInterface
        public void setDark(boolean dark) {
            runOnUiThread(() -> {
                if (dark != darkPage) {
                    darkPage = dark;
                    paintBars();
                }
            });
        }

        @JavascriptInterface
        public void reload() {
            runOnUiThread(() -> {
                server = primary;            // «Повторить» — снова с основного адреса
                triedAlt = false;
                loadApp();
            });
        }

        // ---------- уведомления (без Google-сервисов, см. Push.java)
        @JavascriptInterface
        public boolean pushSupported() {
            return true;
        }

        @JavascriptInterface
        public boolean pushPermission() {
            return Push.canNotify(MainActivity.this);
        }

        /** Включить/выключить уведомления; при включении на Android 13+ один раз спросим разрешение. */
        @JavascriptInterface
        public void setPush(boolean on) {
            runOnUiThread(() -> {
                try {
                    Push.setEnabled(MainActivity.this, on, server);
                    if (on && Build.VERSION.SDK_INT >= 33 && !Push.canNotify(MainActivity.this)
                            && !prefs.getBoolean("asked_notif", false)) {
                        prefs.edit().putBoolean("asked_notif", true).apply();
                        requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 7);
                    }
                } catch (Throwable t) {
                    CrashLog.save(MainActivity.this, t);       // уведомления не должны ронять приложение
                }
            });
        }

        /** Последняя ошибка приложения (веб-приложение отправит её в «Мониторинг»), после чтения стирается. */
        @JavascriptInterface
        public String lastCrash() {
            return CrashLog.take(MainActivity.this);
        }

        /** Пользователь сам включил уведомления переключателем — если Android их запретил, открываем настройки. */
        @JavascriptInterface
        public void openNotificationSettings() {
            runOnUiThread(() -> {
                try {
                    startActivity(new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, getPackageName()));
                } catch (Throwable ignored) {}
            });
        }

        /** «Поделиться» картинкой (итоги семестра): PNG в base64 + текст. */
        @JavascriptInterface
        public void shareImage(String base64, String text) {
            runOnUiThread(() -> {
                try {
                    byte[] data = Base64.decode(base64, Base64.DEFAULT);
                    try (FileOutputStream os = new FileOutputStream(new File(getCacheDir(), ApkProvider.SHARE))) { os.write(data); }
                    Intent i = new Intent(Intent.ACTION_SEND);
                    i.setType("image/png");
                    i.putExtra(Intent.EXTRA_STREAM, ApkProvider.shareUri());
                    if (text != null) i.putExtra(Intent.EXTRA_TEXT, text);
                    i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    startActivity(Intent.createChooser(i, "Поделиться итогами"));
                } catch (Exception e) {
                    Toast.makeText(MainActivity.this, "Не удалось поделиться", Toast.LENGTH_SHORT).show();
                }
            });
        }

        @JavascriptInterface
        public void resetServer() {
            runOnUiThread(() -> {
                prefs.edit().remove("token").remove("token:" + server).apply();
                askServer(null);
            });
        }
    }
}
