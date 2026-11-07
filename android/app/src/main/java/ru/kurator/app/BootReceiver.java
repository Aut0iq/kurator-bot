package ru.kurator.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** После перезагрузки телефона или обновления приложения — снова ставим проверку и будильники опросов. */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context c, Intent in) {
        if (!Push.enabled(c)) return;
        final PendingResult pending = goAsync();
        Push.schedule(c);
        new Thread(() -> {
            try { Push.sync(c.getApplicationContext()); } finally { pending.finish(); }
        }).start();
    }
}
