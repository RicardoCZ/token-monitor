"""
Token Monitor - CDP 服务
通过 Chrome DevTools Protocol 连接浏览器
"""

import json
import websocket
import httpx
from typing import Optional, List, Dict, Any


class CDPService:
    """CDP 服务类"""
    
    def __init__(self):
        self.ws_url: Optional[str] = None
        self.msg_id = 0
        # 默认连接配置
        self.host: str = "127.0.0.1"
        self.port: int = 9223
    
    def _get_next_id(self) -> int:
        self.msg_id += 1
        return self.msg_id
    
    def _send_command(self, ws_url: str, method: str, params: dict = None) -> Optional[Dict]:
        """发送 CDP 命令并等待响应"""
        if not ws_url:
            return None
        
        try:
            if not ws_url.startswith("ws://") and not ws_url.startswith("wss://"):
                ws_url = "ws://" + ws_url
            
            ws = websocket.create_connection(ws_url, timeout=10)
            
            msg_id = self._get_next_id()
            cmd = {"id": msg_id, "method": method}
            if params:
                cmd["params"] = params
            
            ws.send(json.dumps(cmd))
            result = ws.recv()
            ws.close()
            
            return json.loads(result) if result else None
        except Exception as e:
            print(f"CDP command failed: {e}")
            return None
    
    def get_targets(self, host: str = None, port: int = None) -> List[Dict[str, Any]]:
        """获取可用的页面列表
        
        Args:
            host: Chrome 调试地址，默认 127.0.0.1
            port: Chrome 调试端口，默认 9223
        """
        # 使用传入参数或默认值
        cdp_host = host or self.host
        cdp_port = port or self.port
        base_url = f"http://{cdp_host}:{cdp_port}"
        
        try:
            # 首先获取版本信息中的 WebSocket URL
            resp = httpx.get(f"{base_url}/json/version", timeout=5)
            if resp.status_code == 200:
                version_info = resp.json()
                self.ws_url = version_info.get("webSocketDebuggerUrl", "")
            
            # 获取完整的 target 列表
            resp = httpx.get(f"{base_url}/json", timeout=5)
            if resp.status_code == 200:
                targets = resp.json()
                return [
                    {
                        "id": t.get("id", ""),
                        "title": t.get("title", "未知"),
                        "url": t.get("url", ""),
                        "type": t.get("type", "page"),
                        "websocketUrl": t.get("webSocketDebuggerUrl", "")
                    }
                    for t in targets if t.get("type") == "page"
                ]
            return []
        except Exception as e:
            print(f"Get targets failed: {e}")
            return []
    
    def get_cookies_from_target(self, target_ws_url: str, domain: str = "") -> Dict[str, str]:
        """从指定 target 获取 cookies"""
        try:
            # 获取所有 cookies
            result = self._send_command(target_ws_url, "Network.getAllCookies")
            
            if result and "result" in result:
                cookies = result["result"].get("cookies", [])
                
                if domain:
                    # 过滤指定域名的 cookies
                    domain_cookies = [
                        c for c in cookies 
                        if domain in c.get("domain", "")
                    ]
                    return {c["name"]: c["value"] for c in domain_cookies}
                else:
                    return {c["name"]: c["value"] for c in cookies}
            return {}
        except Exception as e:
            print(f"Get cookies failed: {e}")
            return {}
    
    def execute_js(self, target_ws_url: str, expression: str) -> Optional[Dict]:
        """在页面上执行 JavaScript"""
        try:
            result = self._send_command(
                target_ws_url, 
                "Runtime.evaluate", 
                {"expression": expression}
            )
            
            if result and "result" in result:
                return result["result"]
            return None
        except Exception as e:
            print(f"Execute JS failed: {e}")
            return None
    
    def extract_page_data(self, target_ws_url: str) -> Dict[str, Any]:
        """从页面提取完整数据（JavaScript 注入）"""
        js = """
        (function() {
            var result = {};
            try {
                var allText = document.body.innerText || '';
                result.allText = allText;
                
                // 从 localStorage 的 user_detail 提取 groupId
                try {
                    var userDetail = localStorage.getItem('user_detail');
                    if (userDetail) {
                        var userData = JSON.parse(userDetail);
                        if (userData.groups && userData.groups.length > 0) {
                            result.groupId = userData.groups[0];
                        }
                        if (userData.subject_id) {
                            result.subject_id = userData.subject_id;
                        }
                    }
                } catch(e) {}
                
                // 尝试从 URL 或页面中提取 groupId（备用）
                if (!result.groupId) {
                    var url = window.location.href;
                    var groupIdMatch = url.match(/groupId=([a-f0-9-]+)/i);
                    if (groupIdMatch) {
                        result.groupId = groupIdMatch[1];
                    }
                }
                
                var lines = allText.split('\\n');
                for (var i = 0; i < lines.length; i++) {
                    var line = lines[i].trim();
                    
                    if (line.indexOf('截止日期') >= 0) {
                        var match = line.match(/(\\d{2}\\/\\d{2}\\/\\d{4})/);
                        if (match) result.expiresAt = match[1];
                    }
                    if (line.indexOf('重置时间') >= 0) {
                        var matchMin = line.match(/(\\d+)\\s*分钟/);
                        var matchHour = line.match(/(\\d+)\\s*小时/);
                        if (matchMin) result.resetMinutes = parseInt(matchMin[1]);
                        if (matchHour) result.resetHours = parseInt(matchHour[1]);
                    }
                }
                
                var usageMatch = allText.match(/(\\d+)\\s*\\/\\s*(\\d+)/);
                if (usageMatch) {
                    result.used = parseInt(usageMatch[1]);
                    result.total = parseInt(usageMatch[2]);
                }
            } catch(e) {
                result.error = e.message;
            }
            return JSON.stringify(result);
        })()
        """
        
        result = self.execute_js(target_ws_url, js)
        if result and "result" in result:
            remote_obj = result["result"]
            # CDP 返回的是 RemoteObject，如果是 string 类型，值在 value 字段
            if remote_obj.get("type") == "string" and "value" in remote_obj:
                try:
                    return json.loads(remote_obj["value"])
                except:
                    return {"raw": remote_obj["value"]}
            return remote_obj
        return {}

    def extract_minimax_subscription_expires(self, target_ws_url: str) -> str:
        """
        在当前页用 Runtime.evaluate 查找「截止日期」旁的日期，返回 YYYY-MM-DD；失败或无则返回 ""。
        """
        js = r"""
        (function() {
            function normalize(m, d, y) {
                var mm = String(m).padStart(2, '0');
                var dd = String(d).padStart(2, '0');
                return y + '-' + mm + '-' + dd;
            }
            function pickFromText(text) {
                if (!text) return '';
                var t = String(text);
                var m = t.match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
                if (m) return normalize(m[1], m[2], m[3]);
                m = t.match(/(\d{4})-(\d{2})-(\d{2})/);
                if (m) return m[0];
                return '';
            }
            function findExpires() {
                if (!document.body) return '';
                var inner = document.body.innerText || '';
                if (inner.indexOf('截止日期') < 0) return '';
                var lines = inner.split(/\r?\n/);
                for (var i = 0; i < lines.length; i++) {
                    if (lines[i].indexOf('截止日期') >= 0) {
                        var got = pickFromText(lines[i]);
                        if (got) return got;
                        if (i + 1 < lines.length) {
                            got = pickFromText(lines[i + 1]);
                            if (got) return got;
                        }
                    }
                }
                var els = document.querySelectorAll('*');
                for (var j = 0; j < els.length; j++) {
                    var el = els[j];
                    var txt = el.innerText || '';
                    if (txt.length > 200) continue;
                    if (txt.indexOf('截止日期') >= 0) {
                        var got2 = pickFromText(txt);
                        if (got2) return got2;
                    }
                }
                return '';
            }
            return JSON.stringify({ expiresAt: findExpires() });
        })()
        """

        try:
            raw = self.execute_js(target_ws_url, js)
            if raw and "result" in raw:
                remote_obj = raw["result"]
                if remote_obj.get("type") == "string" and "value" in remote_obj:
                    payload = json.loads(remote_obj["value"])
                    return (payload.get("expiresAt") or "").strip()
        except Exception as e:
            print(f"extract_minimax_subscription_expires: {e}")
        return ""


# 全局 CDP 实例
cdp_service = CDPService()
