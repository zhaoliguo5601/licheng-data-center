package com.licheng.datacenter;

import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;
import androidx.core.view.WindowCompat;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    private boolean fellBack = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        enableEdgeToEdge();
        installOfflineFallback();
        // 启动时后台检查 APP 本体是否有新版本（OTA 覆盖安装）
        UpdateManager.checkForUpdate(this);
    }

    /**
     * 断网兜底：正常走线上页面（改样式不用重发版），首次主框架加载失败时
     * 自动切到安装包里自带的那份，避免白屏。只切换一次，防止来回跳。
     */
    private void installOfflineFallback() {
        final WebView wv = getBridge().getWebView();
        if (wv == null) return;
        final WebViewClient orig = wv.getWebViewClient();
        if (orig == null) return;

        wv.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                return orig.shouldOverrideUrlLoading(v, r);
            }

            @Override
            public void onPageStarted(WebView v, String url, android.graphics.Bitmap favicon) {
                orig.onPageStarted(v, url, favicon);
            }

            @Override
            public void onPageFinished(WebView v, String url) {
                orig.onPageFinished(v, url);
            }

            @Override
            public WebResourceResponse shouldInterceptRequest(WebView v, WebResourceRequest r) {
                return orig.shouldInterceptRequest(v, r);
            }

            @Override
            public void onReceivedError(WebView v, WebResourceRequest r, WebResourceError e) {
                orig.onReceivedError(v, r, e);
                if (r != null && r.isForMainFrame()) fallback(v);
            }

            @Override
            public void onReceivedHttpError(WebView v, WebResourceRequest r, WebResourceResponse e) {
                orig.onReceivedHttpError(v, r, e);
                int code = (e != null && e.getStatusCode() > 0) ? e.getStatusCode() : 0;
                if (r != null && r.isForMainFrame() && code >= 500) fallback(v);
            }
        });
    }

    private void fallback(WebView v) {
        if (fellBack) return;
        fellBack = true;
        Toast.makeText(this, "网络不可用，已切换到离线版", Toast.LENGTH_SHORT).show();
        v.post(() -> v.loadUrl("https://localhost/index.html"));
    }

    @Override
    public void onResume() {
        super.onResume();
        // 从系统「安装未知应用」设置页返回后，若已授权则自动继续安装待装包
        UpdateManager.onResume(this);
    }

    /**
     * 沉浸式全屏：状态栏 / 底部导航栏透明，WebView 内容铺满到屏幕上下边缘，
     * 不再保留上下灰色系统栏边框；状态栏与导航栏图标保持亮色以适配深色背景。
     */
    private void enableEdgeToEdge() {
        Window window = getWindow();
        // 不把系统栏内边距塞进内容视图，内容可延伸到状态栏与导航栏区域
        WindowCompat.setDecorFitsSystemWindows(window, false);
        window.setStatusBarColor(Color.TRANSPARENT);
        window.setNavigationBarColor(Color.TRANSPARENT);

        View decor = window.getDecorView();
        int flags = View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION;
        decor.setSystemUiVisibility(flags);

        // API 28+：刘海 / 打孔屏区域也允许内容延伸到边缘
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            window.getAttributes().layoutInDisplayCutoutMode =
                    WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;
        }
    }
}
