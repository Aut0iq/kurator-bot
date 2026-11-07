package ru.kurator.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;


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
