package com.tokenmonitor.app;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        // 注册自定义插件
        registerPlugin(WebViewPlugin.class);
        
        super.onCreate(savedInstanceState);
    }
}
