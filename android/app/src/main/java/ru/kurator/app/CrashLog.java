package ru.kurator.app;

import android.content.Context;
import android.os.Build;

import java.io.PrintWriter;
import java.io.StringWriter;


final class CrashLog {
    private CrashLog() {}

    static void install(Context c) {
        final Context app = c.getApplicationContext();
        final Thread.UncaughtExceptionHandler prev = Thread.getDefaultUncaughtExceptionHandler();
        if (prev instanceof Handler) return;
        Thread.setDefaultUncaughtExceptionHandler(new Handler(app, prev));
    }

    static void save(Context c, Throwable t) {
        try {
            StringWriter sw = new StringWriter();
            t.printStackTrace(new PrintWriter(sw));
            String text = "Android " + Build.VERSION.RELEASE + " (API " + Build.VERSION.SDK_INT + "), " + Build.MANUFACTURER + " " + Build.MODEL
                    + ", версия " + Push.versionName(c) + "\n" + sw;
            Push.prefs(c).edit().putString("last_crash", text.length() > 4000 ? text.substring(0, 4000) : text).commit();
        } catch (Throwable ignored) {}
    }

    static String take(Context c) {
        String s = Push.prefs(c).getString("last_crash", "");
        if (!s.isEmpty()) Push.prefs(c).edit().remove("last_crash").apply();
        return s;
    }

    private static final class Handler implements Thread.UncaughtExceptionHandler {
        private final Context app;
        private final Thread.UncaughtExceptionHandler prev;

        Handler(Context app, Thread.UncaughtExceptionHandler prev) { this.app = app; this.prev = prev; }

        @Override
        public void uncaughtException(Thread th, Throwable e) {
            save(app, e);

            if (th != android.os.Looper.getMainLooper().getThread()) return;
            if (prev != null) prev.uncaughtException(th, e);
        }
    }
}
