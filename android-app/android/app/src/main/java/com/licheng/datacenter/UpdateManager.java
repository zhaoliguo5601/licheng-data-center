package com.licheng.datacenter;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.util.TypedValue;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AlertDialog;
import androidx.core.content.FileProvider;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * APP 本体在线升级（OTA）。
 *
 * 流程：启动时后台拉取远端 version.json → 与本机 versionCode 比对 →
 * 有新版弹确认框 → 带进度条下载 APK 到缓存目录 → 检查「安装未知应用」权限
 * （未授权则引导到系统设置，返回后自动续装）→ 调系统安装器覆盖安装。
 *
 * 下载加固（v1.5）：
 * - 连接超时 15s、读取超时 45s；
 * - 双线路自动切换：主线路失败后切备用线路（备用地址由 version.json 动态下发，
 *   避免写死快照导致下到旧版本包）；
 * - 每条线路最多 3 次重试，阶梯间隔 2s / 4s / 6s；
 * - 支持 Range 断点续传，重试/切线路都不从头拉取已下载部分；
 * - 多次失败后弹窗提供「复制下载链接」（优先备用线路），可到浏览器手动下载兜底。
 *
 * 说明：
 * - 网页/看板功能走远端站点更新，不走这里；这里只负责原生壳本身的升级。
 * - 覆盖安装要求新旧包签名一致；正式发版需固定一套 keystore。
 * - 下载/解析失败不阻断正常使用，弹窗提示原因。
 */
public class UpdateManager {

    private static final String VERSION_URL = "https://lcdc.pages.dev/version.json";
    private static final ExecutorService IO = Executors.newSingleThreadExecutor();
    private static final Handler MAIN = new Handler(Looper.getMainLooper());

    private static final int MAX_RETRY = 3;
    private static final int CONNECT_TIMEOUT = 15000;
    private static final int READ_TIMEOUT = 45000;
    /** 阶梯重试间隔：第 1 次重试等 2s，第 2 次等 4s，第 3 次等 6s。 */
    private static final long[] RETRY_DELAYS_MS = {2000L, 4000L, 6000L};
    /** 主线路整体失败、切到备用线路前的等待。 */
    private static final long SWITCH_DELAY_MS = 2000L;

    /** 下载完成、等待安装的 APK（含授权返回后续装场景） */
    private static File pendingApk;
    private static AlertDialog progressDialog;
    private static ProgressBar progressBar;
    private static TextView progressText;

    public static void checkForUpdate(final Activity activity) {
        if (activity == null) return;
        final int localCode;
        try {
            localCode = activity.getPackageManager()
                    .getPackageInfo(activity.getPackageName(), 0).versionCode;
        } catch (Exception ignored) {
            return;
        }
        IO.execute(() -> {
            try {
                URL url = new URL(VERSION_URL);
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setConnectTimeout(CONNECT_TIMEOUT);
                conn.setReadTimeout(CONNECT_TIMEOUT);
                conn.setRequestMethod("GET");
                conn.setInstanceFollowRedirects(true);
                int code = conn.getResponseCode();
                if (code != 200) return;

                InputStream is = conn.getInputStream();
                StringBuilder sb = new StringBuilder();
                byte[] buf = new byte[4096];
                int n;
                while ((n = is.read(buf)) != -1) sb.append(new String(buf, 0, n, "UTF-8"));
                is.close();
                conn.disconnect();

                JSONObject json = new JSONObject(sb.toString());
                int newCode = json.optInt("versionCode", 0);
                String newName = json.optString("versionName", "");
                String changelog = json.optString("changelog", "");
                String apkUrl = json.optString("apkUrl", "");
                String apkUrlBackup = json.optString("apkUrlBackup", "");
                boolean force = json.optBoolean("force", false);

                if (newCode > localCode && !apkUrl.isEmpty()) {
                    MAIN.post(() -> promptUpdate(activity, newName, changelog,
                            apkUrl, apkUrlBackup, force));
                }
            } catch (Exception ignored) {
                // 网络不可达或清单异常：不阻断使用
            }
        });
    }

    private static void promptUpdate(final Activity activity, String versionName,
                                     String changelog, String apkUrl,
                                     String apkUrlBackup, boolean force) {
        String message = "新版本 " + versionName + "\n\n" + (changelog.isEmpty() ? "有更新可用。" : changelog);
        AlertDialog.Builder builder = new AlertDialog.Builder(activity)
                .setTitle("发现新版本")
                .setMessage(message)
                .setCancelable(!force)
                .setPositiveButton("立即更新", (d, w) -> downloadAndInstall(activity, apkUrl, apkUrlBackup));
        if (!force) {
            builder.setNegativeButton("稍后再说", null);
        }
        builder.show();
    }

    private static void downloadAndInstall(final Activity activity,
                                           String apkUrl, String apkUrlBackup) {
        showProgress(activity);
        IO.execute(() -> {
            File apk = new File(activity.getCacheDir(), "update.apk");
            List<String> urls = buildUrls(apkUrl, apkUrlBackup);
            // 兜底复制链接：优先备用线路，无备用则主线路。
            final String copyUrl = (apkUrlBackup != null && !apkUrlBackup.isEmpty())
                    ? apkUrlBackup : apkUrl;
            try {
                File result = downloadWithRetry(urls, apk);
                pendingApk = result;
                MAIN.post(() -> {
                    dismissProgress();
                    requestInstallPermission(activity, result);
                });
            } catch (Exception e) {
                final String reason = e.getMessage() == null ? "网络异常" : e.getMessage();
                MAIN.post(() -> {
                    dismissProgress();
                    showError(activity, "更新下载失败：" + reason, copyUrl);
                });
            }
        });
    }

    /** 组装下载线路：主线路在前，备用线路去重后追加。 */
    private static List<String> buildUrls(String main, String backup) {
        List<String> urls = new ArrayList<>();
        if (main != null && !main.isEmpty()) urls.add(main);
        if (backup != null && !backup.isEmpty() && !backup.equals(main)) urls.add(backup);
        return urls;
    }

    /**
     * 多线路 + 阶梯重试。每条线路最多 MAX_RETRY 次；已下载的半截包保留以便断点续传。
     * 一条线路全部失败后短暂等待，再切下一条线路。
     */
    private static File downloadWithRetry(List<String> urls, File apk) throws Exception {
        Exception last = null;
        for (int li = 0; li < urls.size(); li++) {
            String url = urls.get(li);
            for (int attempt = 1; attempt <= MAX_RETRY; attempt++) {
                try {
                    return downloadOnce(url, apk);
                } catch (Exception e) {
                    last = e;
                    if (attempt < MAX_RETRY) {
                        sleep(RETRY_DELAYS_MS[attempt - 1]);
                    }
                }
            }
            // 本线路三次全失败，切下一条线路前等待。
            if (li < urls.size() - 1) sleep(SWITCH_DELAY_MS);
        }
        throw last != null ? last : new Exception("下载失败，请稍后重试");
    }

    /**
     * 单次下载。若本地已有半截包则带 Range 请求续传（206 追加写）；
     * 服务端不支持续传返回 200 时从头覆盖写。
     */
    private static File downloadOnce(String apkUrl, File apk) throws Exception {
        long existing = apk.exists() ? apk.length() : 0;
        HttpURLConnection conn = (HttpURLConnection) new URL(apkUrl).openConnection();
        conn.setConnectTimeout(CONNECT_TIMEOUT);
        conn.setReadTimeout(READ_TIMEOUT);
        conn.setInstanceFollowRedirects(true);
        conn.setRequestProperty("Accept-Encoding", "identity");
        if (existing > 0) {
            conn.setRequestProperty("Range", "bytes=" + existing + "-");
        }

        int code = conn.getResponseCode();
        boolean resume = code == 206 && existing > 0;
        if (code != HttpURLConnection.HTTP_OK && !resume) {
            throw new Exception("下载失败 HTTP " + code);
        }

        long remaining = conn.getContentLength();
        long base = resume ? existing : 0;
        long total = remaining > 0 ? base + remaining : -1;

        FileOutputStream fos = new FileOutputStream(apk, resume);
        long done = base;
        InputStream is = conn.getInputStream();
        byte[] buf = new byte[8192];
        int n;
        while ((n = is.read(buf)) != -1) {
            fos.write(buf, 0, n);
            done += n;
            final long fDone = done;
            final long fTotal = total;
            MAIN.post(() -> updateProgress(fDone, fTotal));
        }
        fos.flush();
        fos.close();
        is.close();
        conn.disconnect();

        if (!apk.exists() || apk.length() <= 0) {
            throw new Exception("安装包为空，请稍后重试");
        }
        return apk;
    }

    private static void sleep(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
        }
    }

    /** 安装前检查「安装未知应用」权限；未授权先引导到系统设置。 */
    private static void requestInstallPermission(final Activity activity, final File apk) {
        if (canInstall(activity)) {
            installApk(activity, apk);
            return;
        }
        new AlertDialog.Builder(activity)
                .setTitle("需要安装权限")
                .setMessage("安装更新前，需要先允许本应用「安装未知应用」。\n\n请在接下来打开的系统页面中把开关打开，然后返回本应用，更新会自动继续安装。")
                .setCancelable(false)
                .setPositiveButton("去设置", (d, w) -> {
                    try {
                        Intent intent = new Intent(
                                Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                                Uri.parse("package:" + activity.getPackageName()));
                        activity.startActivity(intent);
                    } catch (Exception ex) {
                        try {
                            activity.startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES));
                        } catch (Exception ex2) {
                            showError(activity, "无法打开权限设置，请手动在系统设置中允许本应用安装未知应用", null);
                        }
                    }
                })
                .setNegativeButton("取消", (d, w) -> pendingApk = null)
                .show();
    }

    /** 从系统设置返回后调用：若已授权且有待装包，自动接着安装。 */
    public static void onResume(Activity activity) {
        if (pendingApk != null && pendingApk.exists() && canInstall(activity)) {
            File apk = pendingApk;
            pendingApk = null;
            installApk(activity, apk);
        }
    }

    private static boolean canInstall(android.content.Context ctx) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            return ctx.getPackageManager().canRequestPackageInstalls();
        }
        return true;
    }

    private static void installApk(Activity activity, File apk) {
        try {
            Uri uri = FileProvider.getUriForFile(
                    activity, activity.getPackageName() + ".fileprovider", apk);
            Intent intent = new Intent(Intent.ACTION_INSTALL_PACKAGE);
            intent.setDataAndType(uri, "application/vnd.android.package-archive");
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            intent.putExtra(Intent.EXTRA_NOT_UNKNOWN_SOURCE, false);

            if (activity.getPackageManager().resolveActivity(intent, 0) == null) {
                showError(activity, "未找到可用的安装器，请手动打开下载的更新包安装", null);
                return;
            }
            activity.startActivity(intent);
        } catch (Exception e) {
            showError(activity, "无法拉起安装器：" + (e.getMessage() == null ? "请检查安装权限" : e.getMessage()), null);
        }
    }

    // ---------- 进度对话框 ----------

    private static void showProgress(Activity activity) {
        LinearLayout box = new LinearLayout(activity);
        box.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(activity, 20);
        box.setPadding(pad, pad, pad, pad);

        progressBar = new ProgressBar(activity, null, android.R.attr.progressBarStyleHorizontal);
        progressBar.setMax(100);
        progressText = new TextView(activity);
        progressText.setPadding(0, dp(activity, 12), 0, 0);

        box.addView(progressBar);
        box.addView(progressText);

        progressDialog = new AlertDialog.Builder(activity)
                .setTitle("正在下载更新")
                .setView(box)
                .setCancelable(false)
                .create();
        progressDialog.show();
        updateProgress(0, -1);
    }

    private static void updateProgress(long done, long total) {
        if (progressBar == null || progressText == null) return;
        if (total > 0) {
            progressBar.setIndeterminate(false);
            int pct = (int) Math.min(100, done * 100 / total);
            progressBar.setProgress(pct);
            progressText.setText(formatSize(done) + " / " + formatSize(total) + "（" + pct + "%）");
        } else {
            progressBar.setIndeterminate(true);
            progressText.setText("已下载 " + formatSize(done) + "…");
        }
    }

    private static void dismissProgress() {
        if (progressDialog != null && progressDialog.isShowing()) {
            progressDialog.dismiss();
        }
        progressDialog = null;
        progressBar = null;
        progressText = null;
    }

    private static void showError(Activity activity, String message, String apkUrl) {
        AlertDialog.Builder builder = new AlertDialog.Builder(activity)
                .setTitle("提示")
                .setMessage(message)
                .setPositiveButton("知道了", null);
        if (apkUrl != null && !apkUrl.isEmpty()) {
            builder.setNeutralButton("复制下载链接", (d, w) -> copyLink(activity, apkUrl));
        }
        builder.show();
    }

    private static void copyLink(Context ctx, String link) {
        try {
            ClipboardManager cm = (ClipboardManager) ctx.getSystemService(Context.CLIPBOARD_SERVICE);
            ClipData clip = ClipData.newPlainText("更新包下载地址", link);
            cm.setPrimaryClip(clip);
            Toast.makeText(ctx, "下载链接已复制，可到浏览器粘贴下载", Toast.LENGTH_LONG).show();
        } catch (Exception e) {
            Toast.makeText(ctx, "复制失败，请手动记录下载地址", Toast.LENGTH_SHORT).show();
        }
    }

    private static int dp(android.content.Context ctx, int value) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value,
                ctx.getResources().getDisplayMetrics());
    }

    private static String formatSize(long bytes) {
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1024 * 1024) return String.format("%.1f KB", bytes / 1024.0);
        return String.format("%.2f MB", bytes / (1024.0 * 1024));
    }
}
