package com.tokenmonitor.app;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "WebViewPlugin")
public class WebViewPlugin extends Plugin {
    
    private static final int WEBVIEW_REQUEST_CODE = 1001;
    private PluginCall savedCall;
    
    @PluginMethod
    public void openLogin(PluginCall call) {
        String url = call.getString("url");
        String cookieDomain = call.getString("cookieDomain");
        
        if (url == null) {
            call.reject("URL is required");
            return;
        }
        
        savedCall = call;
        
        Intent intent = new Intent(getContext(), WebViewActivity.class);
        intent.putExtra("url", url);
        intent.putExtra("cookieDomains", cookieDomain != null ? cookieDomain : "");
        
        startActivityForResult(call, intent, WEBVIEW_REQUEST_CODE);
    }
    
    @PluginMethod
    public void getExtractedCookies(PluginCall call) {
        SharedPreferences prefs = getContext().getSharedPreferences("cookies", Context.MODE_PRIVATE);
        String cookies = prefs.getString("extracted_cookies", "");
        String pageData = prefs.getString("page_data", "{}");
        String groupId = prefs.getString("group_id", "");
        
        JSObject result = new JSObject();
        result.put("cookies", cookies);
        result.put("pageData", pageData);
        result.put("groupId", groupId);  // 同时返回 groupId
        call.resolve(result);
    }
    
    @PluginMethod
    public void clearExtractedCookies(PluginCall call) {
        SharedPreferences prefs = getContext().getSharedPreferences("cookies", Context.MODE_PRIVATE);
        prefs.edit().clear().apply();
        call.resolve();
    }
    
    @Override
    protected void handleOnActivityResult(int requestCode, int resultCode, Intent data) {
        super.handleOnActivityResult(requestCode, resultCode, data);
        
        if (requestCode == WEBVIEW_REQUEST_CODE && savedCall != null) {
            JSObject result = new JSObject();
            result.put("success", true);
            savedCall.resolve(result);
            savedCall = null;
        }
    }
}
