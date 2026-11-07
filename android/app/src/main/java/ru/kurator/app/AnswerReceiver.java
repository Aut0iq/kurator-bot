package ru.kurator.app;

import android.app.Notification;
import android.app.NotificationManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

import org.json.JSONObject;

/** Кнопка в уведомлении опроса: отправляет ответ на сервер (POST /api/poll), не открывая приложение. */
public class AnswerReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context c, Intent in) {
        final PendingResult pending = goAsync();
        final long lid = in.getLongExtra("lesson_id", 0);
        final String date = in.getStringExtra("date"), status = in.getStringExtra("status"), title = in.getStringExtra("title");
        final int id = in.getIntExtra("id", Push.pollId(lid, date));
        new Thread(() -> {
            String text;
            boolean ok = false;
            try {
                JSONObject body = new JSONObject().put("lesson_id", lid).put("date", date).put("status", status);
                JSONObject r = Push.http(c, "POST", "/api/poll", body.toString());
                ok = r.optInt("_status") == 200;
                text = ok ? ("P".equals(status) ? "✅ Ответ принят: буду на паре" : "L".equals(status) ? "⏰ Ответ принят: опоздаю"
                        : "❌ Ответ принят: не смогу. Если причина уважительная — сообщите старосте")
                        : r.optString("error", "Не получилось отправить ответ");
            } catch (Exception e) {
                text = "Нет связи с сервером — откройте приложение и ответьте там";
            }
            NotificationManager nm = c.getSystemService(NotificationManager.class);
            try { if (nm != null) {
                Notification n = new Notification.Builder(c, Push.CH_POLLS)
                        .setSmallIcon(R.drawable.ic_notify)
                        .setColor(Push.ACCENT)
                        .setContentTitle(title == null ? "Куратор +" : title)
                        .setContentText(text)
                        .setStyle(new Notification.BigTextStyle().bigText(text))
                        .setOnlyAlertOnce(true)
                        .setAutoCancel(true)
                        .setTimeoutAfter(ok ? 6000 : 30 * 60 * 1000L)
                        .setContentIntent(Push.openApp(c, "", id))
                        .build();
                nm.notify(id, n);
            } } catch (Throwable t) { CrashLog.save(c, t); }
            finally { pending.finish(); }
        }).start();
    }
}
