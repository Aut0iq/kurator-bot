package ru.kurator.app;

import android.Manifest;
import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.job.JobInfo;
import android.app.job.JobScheduler;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.Build;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Set;


public final class Push {
    static final String PREFS = "kurator";
    static final String CH_POLLS = "polls";
    static final String CH_NEWS = "news";
    static final int JOB_ID = 1001;
    static final int ACCENT = Color.parseColor("#6D5EFC");

    private Push() {}

    static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    static String token(Context c) {
        SharedPreferences p = prefs(c);
        String t = p.getString("token", "");
        return t.isEmpty() ? p.getString("token:" + server(c), "") : t;
    }

    static String server(Context c) {
        SharedPreferences p = prefs(c);
        String s = p.getString("push_server", "");
        return s.isEmpty() ? p.getString("server", "") : s;
    }

    static boolean enabled(Context c) {
        return prefs(c).getBoolean("push_on", false);
    }


    static void channels(Context c) {
        NotificationManager nm = c.getSystemService(NotificationManager.class);
        if (nm == null) return;
        NotificationChannel polls = new NotificationChannel(CH_POLLS, "Опросы перед парой", NotificationManager.IMPORTANCE_HIGH);
        polls.setDescription("«Будешь на паре?» с кнопками ответа");
        polls.enableVibration(true);
        polls.setLightColor(ACCENT);
        NotificationChannel news = new NotificationChannel(CH_NEWS, "Объявления и расписание", NotificationManager.IMPORTANCE_DEFAULT);
        news.setDescription("Объявления, переносы и отмены пар, домашние задания");
        nm.createNotificationChannel(polls);
        nm.createNotificationChannel(news);
    }

    static boolean canNotify(Context c) {
        return Build.VERSION.SDK_INT < 33 || c.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED;
    }


    static void schedule(Context c) {
        try { scheduleJob(c); } catch (Throwable t) { CrashLog.save(c, t); }
    }

    private static void scheduleJob(Context c) {
        JobScheduler js = c.getSystemService(JobScheduler.class);
        if (js == null) return;
        for (JobInfo j : js.getAllPendingJobs()) if (j.getId() == JOB_ID) return;
        JobInfo job = new JobInfo.Builder(JOB_ID, new ComponentName(c, FeedJob.class))
                .setPeriodic(15 * 60 * 1000L)
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setPersisted(true)
                .build();
        js.schedule(job);
    }

    static void stop(Context c) {
        try {
            JobScheduler js = c.getSystemService(JobScheduler.class);
            if (js != null) js.cancel(JOB_ID);
            cancelAlarms(c);
        } catch (Throwable t) { CrashLog.save(c, t); }
    }


    static void setEnabled(Context c, boolean on, String server) {
        SharedPreferences.Editor e = prefs(c).edit().putBoolean("push_on", on);
        if (server != null && !server.isEmpty()) e.putString("push_server", server);
        e.apply();
        if (on) {
            final Context app = c.getApplicationContext();
            try { channels(app); } catch (Throwable t) { CrashLog.save(app, t); }
            schedule(app);
            new Thread(() -> sync(app)).start();
        } else {
            stop(c);
        }
    }


    static JSONObject http(Context c, String method, String path, String body) throws Exception {
        String srv = server(c), tok = token(c);
        if (srv.isEmpty() || tok.isEmpty()) throw new IllegalStateException("not logged in");
        HttpURLConnection h = (HttpURLConnection) new URL(srv + path).openConnection();
        h.setRequestMethod(method);
        h.setConnectTimeout(15000);
        h.setReadTimeout(20000);
        h.setRequestProperty("Authorization", "Bearer " + tok);
        h.setRequestProperty("ngrok-skip-browser-warning", "1");
        h.setRequestProperty("User-Agent", "KuratorApp/" + versionName(c) + " (code " + versionCode(c) + "; Android " + Build.VERSION.RELEASE + ")");
        if (body != null) {
            h.setDoOutput(true);
            h.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            try (OutputStream os = h.getOutputStream()) { os.write(body.getBytes(StandardCharsets.UTF_8)); }
        }
        int code = h.getResponseCode();
        InputStream in = code < 400 ? h.getInputStream() : h.getErrorStream();
        ByteArrayOutputStream bo = new ByteArrayOutputStream();
        if (in != null) {
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) bo.write(buf, 0, n);
            in.close();
        }
        String text = bo.toString("UTF-8");
        JSONObject j = text.trim().startsWith("{") ? new JSONObject(text) : new JSONObject();
        j.put("_status", code);
        return j;
    }

    static String versionName(Context c) {
        try { return c.getPackageManager().getPackageInfo(c.getPackageName(), 0).versionName; } catch (Exception e) { return "1.0"; }
    }

    static long versionCode(Context c) {
        try {
            android.content.pm.PackageInfo pi = c.getPackageManager().getPackageInfo(c.getPackageName(), 0);
            return Build.VERSION.SDK_INT >= 28 ? pi.getLongVersionCode() : pi.versionCode;
        } catch (Exception e) { return 0; }
    }



    static synchronized void sync(Context c) {
        try { doSync(c); } catch (Throwable t) { CrashLog.save(c, t); }
    }

    private static void doSync(Context c) {
        if (!enabled(c) || token(c).isEmpty()) { cancelAlarms(c); return; }
        SharedPreferences p = prefs(c);
        long since = p.getLong("feed_since", -1);
        JSONObject r;
        try {
            r = http(c, "GET", "/api/push/feed" + (since >= 0 ? "?since=" + since : ""), null);
        } catch (Exception e) {
            return;
        }
        int st = r.optInt("_status");
        if (st == 401 || st == 403 || !r.optBoolean("push", false)) { cancelAlarms(c); return; }
        if (st != 200) return;
        channels(c);

        JSONArray ev = r.optJSONArray("events");
        if (since >= 0 && ev != null && canNotify(c)) {
            for (int i = 0; i < ev.length(); i++) {
                JSONObject e = ev.optJSONObject(i);
                if (e != null) { try { showEvent(c, e); } catch (Throwable t) { CrashLog.save(c, t); } }
            }
        }
        p.edit().putLong("feed_since", r.optLong("last", Math.max(since, 0))).apply();
        planPolls(c, r.optJSONArray("polls"), r.optLong("now", System.currentTimeMillis() / 1000));
    }

    private static String hashFor(String kind) {
        if ("announce".equals(kind)) return "announcements";
        if ("homework".equals(kind) || "hw_due".equals(kind)) return "homework";
        return "";
    }

    static PendingIntent openApp(Context c, String hash, int req) {
        Intent i = new Intent(c, MainActivity.class);
        i.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        i.putExtra("hash", hash == null ? "" : hash);
        return PendingIntent.getActivity(c, req, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    static void showEvent(Context c, JSONObject e) {
        NotificationManager nm = c.getSystemService(NotificationManager.class);
        if (nm == null) return;
        String title = e.optString("title", "Куратор +"), body = e.optString("body", "");
        int id = 50000 + (int) (e.optLong("id") % 100000);
        Notification n = new Notification.Builder(c, CH_NEWS)
                .setSmallIcon(R.drawable.ic_notify)
                .setColor(ACCENT)
                .setContentTitle(title)
                .setContentText(body)
                .setStyle(new Notification.BigTextStyle().bigText(body))
                .setAutoCancel(true)
                .setContentIntent(openApp(c, hashFor(e.optString("kind")), id))
                .build();
        nm.notify(id, n);
    }


    static int pollId(long lessonId, String date) {
        return ("poll:" + lessonId + ":" + date).hashCode() & 0x3fffffff;
    }

    private static PendingIntent alarmIntent(Context c, JSONObject poll, int flags) {
        Intent i = new Intent(c, PollAlarm.class);
        i.setAction("ru.kurator.app.POLL");
        i.putExtra("lesson_id", poll.optLong("lesson_id"));
        i.putExtra("date", poll.optString("date"));
        i.putExtra("title", poll.optString("title"));
        i.putExtra("body", poll.optString("body"));
        i.putExtra("close", poll.optLong("close"));
        return PendingIntent.getBroadcast(c, pollId(poll.optLong("lesson_id"), poll.optString("date")), i, flags | PendingIntent.FLAG_IMMUTABLE);
    }

    static void planPolls(Context c, JSONArray polls, long serverNow) {
        cancelAlarms(c);
        if (polls == null) return;
        AlarmManager am = c.getSystemService(AlarmManager.class);
        NotificationManager nm = c.getSystemService(NotificationManager.class);
        if (am == null) return;
        long skew = System.currentTimeMillis() / 1000 - serverNow;
        Set<String> keys = new HashSet<>();
        Set<String> shown = prefs(c).getStringSet("polls_shown", new HashSet<>());
        for (int i = 0; i < polls.length(); i++) {
            JSONObject poll = polls.optJSONObject(i);
            if (poll == null) continue;
            String key = poll.optLong("lesson_id") + ":" + poll.optString("date");
            if (!poll.isNull("answered") && !poll.optString("answered").isEmpty()) {
                if (nm != null) nm.cancel(pollId(poll.optLong("lesson_id"), poll.optString("date")));
                continue;
            }
            if (shown.contains(key)) continue;
            long at = (poll.optLong("at") + skew) * 1000L;
            long close = (poll.optLong("close") + skew) * 1000L;
            long now = System.currentTimeMillis();
            if (close <= now + 30000) continue;
            if (at < now) at = now + 1000;
            PendingIntent pi = alarmIntent(c, poll, PendingIntent.FLAG_UPDATE_CURRENT);


            am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, Math.max(now + 1000, at - 60000), pi);
            keys.add(polls.optJSONObject(i).toString());
        }
        prefs(c).edit().putStringSet("alarms", keys).apply();
    }

    static void cancelAlarms(Context c) {
        AlarmManager am = c.getSystemService(AlarmManager.class);
        Set<String> keys = prefs(c).getStringSet("alarms", new HashSet<>());
        if (am != null) {
            for (String k : keys) {
                try {
                    PendingIntent pi = alarmIntent(c, new JSONObject(k), PendingIntent.FLAG_NO_CREATE);
                    if (pi != null) { am.cancel(pi); pi.cancel(); }
                } catch (Exception ignored) {}
            }
        }
        prefs(c).edit().remove("alarms").apply();
    }

    static void markShown(Context c, String key) {
        Set<String> s = new HashSet<>(prefs(c).getStringSet("polls_shown", new HashSet<>()));
        if (s.size() > 60) s.clear();
        s.add(key);
        prefs(c).edit().putStringSet("polls_shown", s).apply();
    }
}
