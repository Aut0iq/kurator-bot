package ru.kurator.app;

import android.app.Notification;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.graphics.drawable.Icon;

/** Будильник опроса: показывает «Будешь на паре?» с тремя кнопками прямо в уведомлении. */
public class PollAlarm extends BroadcastReceiver {
    static final String[][] ANSWERS = {{"P", "✅ Буду"}, {"L", "⏰ Опоздаю"}, {"A", "❌ Не смогу"}};

    @Override
    public void onReceive(Context c, Intent in) {
        try { handle(c, in); } catch (Throwable t) { CrashLog.save(c, t); }
    }

    private void handle(Context c, Intent in) {
        if (!Push.enabled(c) || !Push.canNotify(c)) return;
        long lid = in.getLongExtra("lesson_id", 0), close = in.getLongExtra("close", 0) * 1000L;
        String date = in.getStringExtra("date");
        if (close > 0 && close < System.currentTimeMillis()) return;          // опрос уже закрыт
        show(c, lid, date, in.getStringExtra("title"), in.getStringExtra("body"), close);
        Push.markShown(c, lid + ":" + date);
    }

    static void show(Context c, long lid, String date, String title, String body, long closeMs) {
        Push.channels(c);
        int id = Push.pollId(lid, date);
        Notification.Builder b = new Notification.Builder(c, Push.CH_POLLS)
                .setSmallIcon(R.drawable.ic_notify)
                .setColor(Push.ACCENT)
                .setContentTitle("🔔 " + title)
                .setContentText(body)
                .setStyle(new Notification.BigTextStyle().bigText(body))
                .setCategory(Notification.CATEGORY_REMINDER)
                .setAutoCancel(true)
                .setOnlyAlertOnce(true)
                .setContentIntent(Push.openApp(c, "", id));
        if (closeMs > System.currentTimeMillis()) b.setTimeoutAfter(closeMs - System.currentTimeMillis());
        for (int k = 0; k < ANSWERS.length; k++) {
            Intent a = new Intent(c, AnswerReceiver.class);
            a.setAction("ru.kurator.app.ANSWER");
            a.putExtra("lesson_id", lid).putExtra("date", date).putExtra("status", ANSWERS[k][0])
             .putExtra("title", title).putExtra("id", id);
            PendingIntent pi = PendingIntent.getBroadcast(c, id * 4 + k, a, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            b.addAction(new Notification.Action.Builder(Icon.createWithResource(c, R.drawable.ic_notify), ANSWERS[k][1], pi).build());
        }
        NotificationManager nm = c.getSystemService(NotificationManager.class);
        if (nm != null) nm.notify(id, b.build());
    }
}
