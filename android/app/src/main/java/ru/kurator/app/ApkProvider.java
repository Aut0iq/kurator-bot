package ru.kurator.app;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;

import java.io.File;
import java.io.FileNotFoundException;

/**
 * Отдаёт картинку «Итоги семестра» приложениям при «Поделиться» (без библиотек androidx).
 * Адрес: content://ru.kurator.app.apk/share.png
 */
public class ApkProvider extends ContentProvider {
    public static final String AUTHORITY = "ru.kurator.app.apk";
    public static final String FILE = "update.apk";

    public static final String SHARE = "share.png";     // картинка «Итоги семестра» для «Поделиться»

    public static Uri uri() {
        return Uri.parse("content://" + AUTHORITY + "/" + FILE);
    }

    public static Uri shareUri() {
        return Uri.parse("content://" + AUTHORITY + "/" + SHARE);
    }

    private static String name(Uri uri) {
        return SHARE;                       // приложение больше не устанавливает обновления само — только «Поделиться»
    }

    @Override
    public boolean onCreate() {
        return true;
    }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        File f = new File(getContext().getCacheDir(), name(uri));
        if (!f.exists()) throw new FileNotFoundException(name(uri));
        return ParcelFileDescriptor.open(f, ParcelFileDescriptor.MODE_READ_ONLY);
    }

    @Override
    public String getType(Uri uri) {
        return SHARE.equals(name(uri)) ? "image/png" : "application/vnd.android.package-archive";
    }

    @Override
    public Cursor query(Uri uri, String[] p, String s, String[] a, String o) {
        // имя и размер файла — их спрашивают мессенджеры при «Поделиться»
        File f = new File(getContext().getCacheDir(), name(uri));
        android.database.MatrixCursor c = new android.database.MatrixCursor(new String[]{
                android.provider.OpenableColumns.DISPLAY_NAME, android.provider.OpenableColumns.SIZE});
        c.addRow(new Object[]{name(uri).equals(SHARE) ? "semestr.png" : FILE, f.length()});
        return c;
    }

    @Override
    public Uri insert(Uri uri, ContentValues v) {
        return null;
    }

    @Override
    public int delete(Uri uri, String s, String[] a) {
        return 0;
    }

    @Override
    public int update(Uri uri, ContentValues v, String s, String[] a) {
        return 0;
    }
}
