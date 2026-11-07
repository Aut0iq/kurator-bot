package ru.kurator.app;

import android.app.job.JobParameters;
import android.app.job.JobService;

/** Раз в ~15 минут (когда есть сеть) забирает ленту уведомлений с сервера. */
public class FeedJob extends JobService {
    @Override
    public boolean onStartJob(JobParameters params) {
        new Thread(() -> {
            try { Push.sync(getApplicationContext()); } finally { jobFinished(params, false); }
        }).start();
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters params) {
        return true;
    }
}
