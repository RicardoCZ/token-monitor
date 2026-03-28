package com.tokenmonitor.app;

import android.app.Activity;
import android.os.Bundle;
import android.util.Log;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.ValueCallback;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.Toast;

import org.json.JSONObject;

public class WebViewActivity extends Activity {
    private static final String TAG = "WebViewActivity";
    private WebView webView;
    private String url;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        
        url = getIntent().getStringExtra("url");
        
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setLayoutParams(new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.MATCH_PARENT
        ));
        
        // 顶部工具栏
        LinearLayout toolbar = new LinearLayout(this);
        toolbar.setOrientation(LinearLayout.HORIZONTAL);
        toolbar.setPadding(16, 16, 16, 16);
        toolbar.setBackgroundColor(0xFF1a1a2e);
        
        Button closeBtn = new Button(this);
        closeBtn.setText("关闭");
        closeBtn.setOnClickListener(v -> finish());
        
        Button extractBtn = new Button(this);
        extractBtn.setText("提取数据");
        extractBtn.setOnClickListener(v -> extractPageData());
        
        toolbar.addView(closeBtn);
        toolbar.addView(extractBtn);
        layout.addView(toolbar);
        
        // WebView
        webView = new WebView(this);
        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setDomStorageEnabled(true);
        
        CookieManager cookieManager = CookieManager.getInstance();
        cookieManager.setAcceptCookie(true);
        cookieManager.setAcceptThirdPartyCookies(webView, true);
        
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                Log.d(TAG, "Page finished: " + url);
            }
        });
        
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, 0, 1.0f
        );
        webView.setLayoutParams(params);
        layout.addView(webView);
        
        setContentView(layout);
        
        if (url != null) {
            webView.loadUrl(url);
        }
    }
    
    private void extractPageData() {
        String currentUrl = webView.getUrl();
        Log.d(TAG, "Current URL: " + currentUrl);
        
        if (currentUrl != null && currentUrl.contains("minimaxi.com")) {
            extractMiniMaxData();
        } else if (currentUrl != null && currentUrl.contains("xfyun.cn")) {
            extractXfyunData();
        } else {
            extractCookies();
        }
    }
    
    private void extractMiniMaxData() {
        // 提取 MiniMax 页面数据
        String js = "(function() {" +
            "var result = {};" +
            "var allText = document.body.innerText;" +
            "var lines = allText.split('\\n');" +
            
            // 查找截止日期
            "for (var i = 0; i < lines.length; i++) {" +
            "    var line = lines[i].trim();" +
            "    if (line.indexOf('截止日期') >= 0) {" +
            "        var match = line.match(/截止日期[：:]\\s*(\\d{2}\\/\\d{2}\\/\\d{4})/);" +
            "        if (match) result.expiresAt = match[1];" +
            "    }" +
            "    if (line.indexOf('重置时间') >= 0) {" +
            "        var matchMin = line.match(/(\\d+)\\s*分钟/);" +
            "        var matchHour = line.match(/(\\d+)\\s*小时/);" +
            "        if (matchMin) result.resetMinutes = matchMin[1];" +
            "        if (matchHour) result.resetHours = matchHour[1];" +
            "    }" +
            "}" +
            
            // 查找使用量
            "var usageMatch = allText.match(/当前使用[\\s\\S]*?(\\d+)\\s*\\/\\s*(\\d+)[\\s\\S]*?(\\d+)%/);" +
            "if (usageMatch) {" +
            "    result.used = usageMatch[1];" +
            "    result.total = usageMatch[2];" +
            "    result.percent = usageMatch[3];" +
            "}" +
            
            "return JSON.stringify(result);" +
        "})();";
        
        webView.evaluateJavascript(js, value -> {
            Log.d(TAG, "MiniMax data: " + value);
            try {
                // 解析 JSON 并保存
                String jsonStr = value.replaceAll("^\"|\"$", "").replace("\\\"", "\"");
                JSONObject data = new JSONObject(jsonStr);
                
                // 同时提取 Cookie
                String cookies = extractCookies();
                
                // 保存所有数据
                getSharedPreferences("cookies", MODE_PRIVATE)
                    .edit()
                    .putString("extracted_cookies", cookies)
                    .putString("page_data", jsonStr)
                    .apply();
                
                boolean hasLogin = cookies.contains("HERTZ-SESSION");
                String msg = hasLogin ? 
                    "✓ 数据已提取（含登录信息）" :
                    "✓ Cookie 已提取";
                Toast.makeText(this, msg, Toast.LENGTH_SHORT).show();
                
            } catch (Exception e) {
                Log.e(TAG, "Parse error", e);
                extractCookies();
            }
        });
    }
    
    private void extractXfyunData() {
        // 提取讯飞页面数据
        String js = "(function() {" +
            "var result = {};" +
            "var allText = document.body.innerText;" +
            
            // 查找到期时间
            "var expireMatch = allText.match(/到期[时间]?[：:]\\s*(\\d{4}[-/]\\d{2}[-/]\\d{2})/);" +
            "if (expireMatch) result.expiresAt = expireMatch[1];" +
            
            // 查找额度
            "var quotaMatch = allText.match(/(\\d+\\.?\\d*)\\s*万/);" +
            "if (quotaMatch) result.dailyQuota = quotaMatch[1];" +
            
            "return JSON.stringify(result);" +
        "})();";
        
        webView.evaluateJavascript(js, value -> {
            Log.d(TAG, "Xfyun data: " + value);
            String cookies = extractCookies();
            
            try {
                String jsonStr = value.replaceAll("^\"|\"$", "").replace("\\\"", "\"");
                getSharedPreferences("cookies", MODE_PRIVATE)
                    .edit()
                    .putString("extracted_cookies", cookies)
                    .putString("page_data", jsonStr)
                    .apply();
            } catch (Exception e) {
                Log.e(TAG, "Parse error", e);
            }
            
            Toast.makeText(this, "✓ 数据已提取", Toast.LENGTH_SHORT).show();
        });
    }
    
    private String extractCookies() {
        CookieManager cookieManager = CookieManager.getInstance();
        
        String[] urlsToTry = {
            "https://platform.minimaxi.com",
            "https://www.minimaxi.com",
            "https://maas.xfyun.cn",
            webView.getUrl()
        };
        
        StringBuilder cookieStr = new StringBuilder();
        
        for (String tryUrl : urlsToTry) {
            if (tryUrl == null) continue;
            String cookies = cookieManager.getCookie(tryUrl);
            if (cookies != null && !cookies.isEmpty()) {
                if (cookieStr.length() > 0) cookieStr.append("; ");
                cookieStr.append(cookies);
            }
        }
        
        return cookieStr.toString();
    }
    
    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
