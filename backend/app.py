#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Token Monitor Backend - 爱丽丝的作品 ✨
监控 MiniMax 和讯飞语音的 token 使用量

架构：前后端分离 + 插件化
- 前端：静态 HTML
- 后端：Flask API + Playwright 浏览器自动化登录
- 插件化：新增供应商只需添加配置，无需修改核心代码
"""

from flask import Flask, jsonify, request, send_from_directory
import requests
import json
import os
import time
import threading
from pathlib import Path

# 禁用代理，让 requests 直连
for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'NO_PROXY', 'no_proxy']:
    os.environ.pop(var, None)

# 创建不使用代理的 requests session
session = requests.Session()
session.proxies = {'http': None, 'https': None}

app = Flask(__name__)

# ============ 路径配置 ============
BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ============ 插件化用量查询配置 ============
# 
# 新增供应商只需在此添加配置，无需编写新函数！
#
# 配置字段说明：
#   id          : 唯一标识
#   name        : 显示名称
#   icon        : emoji 图标
#   domain      : 主域名（用于显示）
#   login_url   : 登录页面 URL
#   cookie_domains: 需要获取 Cookie 的域名列表
#   api         : API 调用配置
#     url       : API 端点
#     method    : GET/POST
#     params    : URL 查询参数（dict 或 callable）
#     headers   : 请求头（dict 或 callable）
#     referer   : Referer 头
#   parse       : 响应解析函数，输入 requests.Response，返回 dict

# MiniMax GroupId - 支持环境变量或从数据文件自动获取
def _get_minimax_group_id():
    """获取 MiniMax GroupId，优先环境变量，其次数据文件"""
    env_id = os.environ.get("MINIMAX_GROUP_ID", "")
    if env_id:
        return env_id
    
    # 从数据文件读取
    cookie_file = get_cookie_file("minimax")
    if os.path.exists(cookie_file):
        try:
            with open(cookie_file, "r") as f:
                data = json.load(f)
            if data.get("group_id"):
                return data["group_id"]
        except:
            pass
    return ""

def _fetch_minimax_group_id(cookies):
    """从 MiniMax API 获取用户的 GroupId"""
    try:
        # 尝试调用用户信息 API
        url = "https://www.minimaxi.com/v1/api/openplatform/current_user_info"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Cookie": cookies,
            "Referer": "https://platform.minimaxi.com/user-center/basic-info/interface-key"
        }
        resp = session.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("base_resp", {}).get("status_code") == 0:
                return data.get("group_id", "")
    except Exception as e:
        print(f"获取 GroupId 失败: {e}")
    return ""

USAGE_PLUGINS = {
    "minimax": {
        "id": "minimax",
        "name": "MiniMax",
        "icon": "🟠",
        "domain": "minimaxi.com",
        "login_url": "https://platform.minimaxi.com/user-center/payment/token-plan",
        "cookie_domains": ["minimaxi.com", "minimax.com"],
        
        "api": {
            "url": "https://www.minimaxi.com/v1/api/openplatform/coding_plan/remains",
            "method": "GET",
            "params": lambda: {"GroupId": _get_minimax_group_id()},
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*"
            },
            "referer": "https://platform.minimaxi.com/user-center/payment/token-plan"
        },
        
        "parse": lambda resp: _parse_minimax(resp)
    },
    
    "xfyun": {
        "id": "xfyun",
        "name": "讯飞星辰",
        "icon": "🔵",
        "domain": "xfyun.cn",
        "login_url": "https://maas.xfyun.cn/packageSubscription?from=packageSubscriptionOverlay",
        "cookie_domains": ["xfyun.cn", "xfyun.com"],
        
        "api": {
            "url": "https://maas.xfyun.cn/api/v1/gpt-finetune/coding-plan/list",
            "method": "GET",
            "params": {},
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*"
            },
            "referer": "https://maas.xfyun.cn/packageSubscription"
        },
        
        "parse": lambda resp: _parse_xfyun(resp)
    }
}

# CDP 支持的服务配置（与 USAGE_PLUGINS 共用）
CDP_SERVICES = [
    {
        "id": p["id"],
        "name": p["name"],
        "icon": p["icon"],
        "domain": p["domain"],
        "login_url": p["login_url"],
        "cookie_domains": p["cookie_domains"]
    }
    for p in USAGE_PLUGINS.values()
]

# ============ 内部解析函数（保持原有逻辑）============

def _parse_minimax(resp):
    """解析 MiniMax API 响应"""
    if resp.status_code == 200:
        resp_data = resp.json()
        base_resp = resp_data.get("base_resp", {})
        
        if base_resp.get("status_code") == 0:
            model_remains = resp_data.get("model_remains", [])
            result = {}
            for m in model_remains:
                model_name = m.get("model_name", "unknown")
                total = m.get("current_interval_total_count", 0)
                usage_count = m.get("current_interval_usage_count", 0)
                remains_time = m.get("remains_time", 0)
                
                used = total - usage_count if total > 0 else 0
                
                result[model_name] = {
                    "total": total,
                    "used": used,
                    "remain": usage_count if total > 0 else remains_time,
                    "remains_time": remains_time
                }
            return result
        elif base_resp.get("status_code") in [1004, 401]:
            return {"error": "MiniMax 登录已过期，请重新登录", "need_login": True}
        else:
            return {"error": f"API 错误: {base_resp.get('status_msg', '未知错误')}"}
    else:
        return {"error": f"HTTP {resp.status_code}"}

def _parse_xfyun(resp):
    """解析讯飞星辰 API 响应"""
    if resp.status_code == 200:
        resp_data = resp.json()
        if resp_data.get("code") == 0:
            rows = resp_data.get("data", {}).get("rows", [])
            if not rows:
                return {"error": "未找到订阅套餐"}
            
            plan = rows[0]
            usage = plan.get("codingPlanUsageDTO", {})
            
            return {
                "appId": plan.get("appId", ""),
                "channel": usage.get("channel", ""),
                "dailyLimit": usage.get("dailyLimit", 0),
                "dailyUsage": usage.get("dailyUsage", 0),
                "dailyRemain": usage.get("dailyLimit", 0) - usage.get("dailyUsage", 0) if usage.get("dailyLimit") else 0,
                "expiresAt": plan.get("expiresAt", "")
            }
        else:
            return {"error": f"API 错误: {resp_data.get('msg', '未知错误')}"}
    else:
        return {"error": f"HTTP {resp.status_code}"}

# ============ Cookie 文件路径 ============

def get_cookie_file(service_id):
    """获取指定服务的 Cookie 文件路径"""
    return os.path.join(DATA_DIR, f"{service_id}_cookies.json")

# ============ 通用用量查询函数（插件化核心）============

def check_usage(service_id):
    """通用的用量查询函数，通过插件化的配置驱动"""
    
    plugin = USAGE_PLUGINS.get(service_id)
    if not plugin:
        return {"error": f"未知服务: {service_id}"}
    
    cookie_file = get_cookie_file(service_id)
    
    # 加载 Cookie
    try:
        if os.path.exists(cookie_file):
            with open(cookie_file, "r") as f:
                data = json.load(f)
        else:
            data = None
    except:
        data = None
    
    if not data or not data.get("cookies"):
        return {"error": f"请先登录 {plugin['name']}", "need_login": True}
    
    cookies = data.get("cookies", "")
    page_info = data.get("page_info")  # 截止日期等页面信息
    
    try:
        api_config = plugin["api"]
        
        # 构建请求
        headers = dict(api_config.get("headers", {}))
        headers["Cookie"] = cookies
        if api_config.get("referer"):
            headers["Referer"] = api_config["referer"]
        
        # 构建 URL 参数
        params = api_config.get("params", {})
        if callable(params):
            params = params()
        
        # 发送请求
        url = api_config["url"]
        method = api_config.get("method", "GET")
        
        if method == "GET":
            response = session.get(url, headers=headers, params=params, timeout=10)
        else:
            response = session.post(url, headers=headers, json=params, timeout=10)
        
        # 解析响应
        result = plugin["parse"](response)
        
        # 如果有 page_info（截止日期），添加到结果中
        if page_info and isinstance(result, dict) and "error" not in result:
            result["page_info"] = page_info
        
        return result
        
    except Exception as e:
        return {"error": str(e)}

# ============ Playwright 登录 ============

playwright_browser = None
playwright_lock = threading.Lock()

def get_playwright():
    """获取或创建 Playwright 浏览器实例"""
    global playwright_browser
    
    with playwright_lock:
        if playwright_browser is None:
            from playwright.sync_api import sync_playwright
            p = sync_playwright().start()
            playwright_browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage']
            )
            return p, playwright_browser
        else:
            from playwright.sync_api import sync_playwright
            p = sync_playwright().start()
            return p, playwright_browser

def close_playwright():
    """关闭 Playwright"""
    global playwright_browser
    with playwright_lock:
        if playwright_browser:
            try:
                playwright_browser.close()
            except:
                pass
            playwright_browser = None

def login_with_playwright(service_id, headless=False):
    """通用的 Playwright 登录函数"""
    
    plugin = USAGE_PLUGINS.get(service_id)
    if not plugin:
        return None
    
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=headless,
                args=['--no-sandbox', '--disable-dev-shm-usage']
            )
            context = browser.new_context(viewport={"width": 1200, "height": 800})
            page = context.new_page()
            
            login_url = plugin["login_url"]
            print(f"[{plugin['name']} Login] 打开登录页面: {login_url}")
            
            page.goto(login_url, wait_until="networkidle", timeout=30000)
            
            # 检查是否已经登录
            try:
                page.wait_for_selector("body", timeout=5000)
                print(f"[{plugin['name']} Login] 页面已加载，获取 Cookie...")
                cookies = context.cookies()
                browser.close()
                return cookies
            except:
                pass
            
            print(f"[{plugin['name']} Login] 等待用户操作...")
            
            # 等待登录完成（通过 URL 判断）
            try:
                page.wait_for_url(f"**/{plugin['domain']}**", timeout=180000)
                print(f"[{plugin['name']} Login] 登录成功！")
                cookies = context.cookies()
                browser.close()
                return cookies
            except Exception as e:
                print(f"[{plugin['name']} Login] 等待登录超时: {e}")
                browser.close()
                return None
                
    except Exception as e:
        print(f"Playwright login error: {e}")
        return None

# ============ CDP 浏览器连接 ============

cdp_browser_ws = None
cdp_target_url = None
cdp_msg_id = 0

def cdp_get_targets(ws_url):
    """获取 CDP 可用的标签页列表"""
    try:
        import urllib.request
        with urllib.request.urlopen(f"http://{ws_url}/json/list", timeout=5) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        return []

def cdp_send_command(ws_url, method, params=None):
    """发送 CDP 命令"""
    try:
        import websocket
        global cdp_msg_id
        
        ws = websocket.create_connection(f"ws://{ws_url}", timeout=10)
        cdp_msg_id += 1
        
        cmd = {"id": cdp_msg_id, "method": method}
        if params:
            cmd["params"] = params
        ws.send(json.dumps(cmd))
        
        result = ws.recv()
        ws.close()
        
        return json.loads(result)
    except Exception as e:
        return {"error": str(e)}

def cdp_execute_js(ws_url, expression):
    """在页面上执行 JavaScript 并返回结果"""
    global cdp_msg_id
    try:
        import websocket
        import json
        
        ws = websocket.create_connection(f"ws://{ws_url}", timeout=10)
        cdp_msg_id += 1
        
        cmd = {
            "id": cdp_msg_id,
            "method": "Runtime.evaluate",
            "params": {"expression": expression}
        }
        ws.send(json.dumps(cmd))
        result = ws.recv()
        ws.close()
        
        data = json.loads(result)
        if "result" in data:
            return {"success": True, "result": data["result"].get("result", {})}
        return {"success": False, "error": "执行失败"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def cdp_get_cookies(ws_url, domain):
    """从指定域获取所有 Cookie"""
    global cdp_msg_id
    try:
        import websocket
        import json
        
        if not ws_url.startswith("ws://") and not ws_url.startswith("wss://"):
            ws_url = "ws://" + ws_url
        
        ws = websocket.create_connection(ws_url, timeout=10)
        cdp_msg_id += 1
        
        cmd = {
            "id": cdp_msg_id,
            "method": "Network.getAllCookies",
            "params": {}
        }
        ws.send(json.dumps(cmd))
        result = ws.recv()
        ws.close()
        
        data = json.loads(result)
        if "result" in data:
            cookies = data["result"].get("cookies", [])
            domain_cookies = [c for c in cookies if domain in c.get("domain", "")]
            return {"success": True, "cookies": domain_cookies}
        return {"success": False, "error": "无法获取 Cookie"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ============ 数据存储 ============

def load_data(file_path):
    try:
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                return json.load(f)
    except:
        pass
    return None

def save_data(file_path, data):
    try:
        with open(file_path, "w") as f:
            json.dump(data, f)
    except:
        pass

# ============ Flask 路由 ============

@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.route("/index.html")
def index_html():
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.route("/setup")
def setup():
    return send_from_directory(FRONTEND_DIR, "setup.html")

@app.route("/api/status")
def status():
    """获取所有服务的状态"""
    result = {}
    for service_id in USAGE_PLUGINS.keys():
        result[service_id] = check_usage(service_id)
    return jsonify(result)

@app.route("/api/<service_id>")
def service_status(service_id):
    """通用服务状态查询"""
    if service_id not in USAGE_PLUGINS:
        return jsonify({"error": f"未知服务: {service_id}"}), 404
    return jsonify(check_usage(service_id))

@app.route("/api/login/start", methods=["POST"])
def login_start():
    """开始登录流程"""
    data = request.get_json() or {}
    service = data.get("service")
    
    if service not in USAGE_PLUGINS:
        return jsonify({"success": False, "error": f"未知服务: {service}"})
    
    def background_login():
        cookies = login_with_playwright(service)
        if cookies:
            cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
            save_data(get_cookie_file(service), {
                "cookies": cookie_str,
                "timestamp": int(time.time() * 1000)
            })
    
    thread = threading.Thread(target=background_login)
    thread.daemon = True
    thread.start()
    
    plugin = USAGE_PLUGINS[service]
    return jsonify({
        "success": True,
        "message": f"浏览器已启动，请在弹出的窗口中完成登录 {plugin['name']}（等待最多2分钟）"
    })

@app.route("/api/login/status")
def login_status():
    """检查所有服务的登录状态"""
    result = {}
    for service_id, plugin in USAGE_PLUGINS.items():
        data = load_data(get_cookie_file(service_id))
        result[service_id] = data is not None and bool(data.get("cookies"))
    return jsonify(result)

@app.route("/api/current-cookies")
def current_cookies():
    """获取当前保存的 Cookie 状态"""
    result = {}
    for service_id, plugin in USAGE_PLUGINS.items():
        data = load_data(get_cookie_file(service_id))
        
        def mask(cookie_str):
            if not cookie_str:
                return ""
            if len(cookie_str) <= 40:
                return cookie_str[:10] + "..."
            return cookie_str[:20] + "..." + cookie_str[-10:]
        
        result[service_id] = {
            "has": data is not None and bool(data.get("cookies")),
            "preview": mask(data.get("cookies", "") if data else "")
        }
    return jsonify(result)

@app.route("/api/login/refresh", methods=["POST"])
def login_refresh():
    """刷新指定服务的 Cookie"""
    data = request.get_json() or {}
    service = data.get("service")
    headless = data.get("headless", True)
    
    if service not in USAGE_PLUGINS:
        return jsonify({"success": False, "error": f"未知服务: {service}"})
    
    cookies = login_with_playwright(service, headless=headless)
    if cookies:
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        save_data(get_cookie_file(service), {
            "cookies": cookie_str,
            "timestamp": int(time.time() * 1000)
        })
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "登录失败或超时"})

@app.route("/api/login/capabilities")
def login_capabilities():
    """检查服务器能力"""
    import subprocess
    has_display = False
    try:
        result = subprocess.run(['xdpyinfo'], capture_output=True, timeout=5)
        has_display = result.returncode == 0
    except:
        pass
    return jsonify({
        "headless_available": True,
        "visible_browser_available": has_display,
        "note": "visible_browser=true 时请使用 headless=false 参数运行登录"
    })

@app.route("/api/set-cookie", methods=["POST"])
def set_cookie():
    """接收前端发送的 Cookie 和页面信息（如截止日期），并自动获取 GroupId"""
    data = request.get_json() or {}
    service = data.get("service")
    cookies = data.get("cookies")
    page_info = data.get("page_info")  # 可选：页面上的其他信息（如截止日期）
    
    if not service or not cookies:
        return jsonify({"success": False, "error": "缺少参数"})
    
    if service not in USAGE_PLUGINS:
        return jsonify({"success": False, "error": f"未知服务: {service}"})
    
    save_dict = {
        "cookies": cookies,
        "page_info": page_info,
        "timestamp": int(time.time() * 1000)
    }
    
    # MiniMax 自动获取 GroupId
    if service == "minimax":
        group_id = os.environ.get("MINIMAX_GROUP_ID", "")
        if not group_id:
            # 尝试从 API 获取 GroupId
            group_id = _fetch_minimax_group_id(cookies)
            print(f"自动获取到 MiniMax GroupId: {group_id}")
        save_dict["group_id"] = group_id
    
    save_data(get_cookie_file(service), save_dict)
    plugin = USAGE_PLUGINS[service]
    return jsonify({"success": True, "message": f"{plugin['name']} Cookie 保存成功"})

# ============ CDP API ============

@app.route("/api/cdp/connect", methods=["POST"])
def cdp_connect():
    """连接到调试浏览器"""
    global cdp_browser_ws, cdp_target_url
    
    data = request.get_json() or {}
    host = data.get("host", "127.0.0.1")
    port = data.get("port", 9222)
    
    ws_url = f"{host}:{port}"
    
    try:
        targets = cdp_get_targets(ws_url)
        if targets is None or (isinstance(targets, list) and len(targets) == 0):
            import websocket
            test_ws = websocket.create_connection(f"ws://{ws_url}", timeout=3)
            test_ws.close()
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"无法连接到 {ws_url}，请确认浏览器已开启远程调试",
            "hint": "在 Chrome 地址栏输入 chrome://inspect/#remote-debugging 勾选允许调试"
        })
    
    cdp_browser_ws = ws_url
    cdp_target_url = None
    
    available_targets = []
    for t in targets:
        available_targets.append({
            "id": t.get("id", ""),
            "title": t.get("title", "未知页面"),
            "url": t.get("url", ""),
            "type": t.get("type", "")
        })
    
    return jsonify({
        "success": True,
        "ws_url": ws_url,
        "targets": available_targets,
        "message": f"已连接到调试浏览器，共 {len(available_targets)} 个可用页面"
    })

@app.route("/api/cdp/status")
def cdp_status():
    """检查 CDP 连接状态"""
    global cdp_browser_ws
    return jsonify({
        "connected": cdp_browser_ws is not None,
        "ws_url": cdp_browser_ws
    })

@app.route("/api/cdp/targets")
def cdp_targets():
    """获取可用目标页面"""
    global cdp_browser_ws
    
    if not cdp_browser_ws:
        return jsonify({"success": False, "error": "未连接到浏览器"})
    
    targets = cdp_get_targets(cdp_browser_ws)
    available = []
    for t in targets:
        available.append({
            "id": t.get("id", ""),
            "title": t.get("title", "未知"),
            "url": t.get("url", ""),
            "type": t.get("type", "")
        })
    
    return jsonify({"success": True, "targets": available})

@app.route("/api/cdp/set-target", methods=["POST"])
def cdp_set_target():
    """设置当前活动的目标页面"""
    global cdp_browser_ws, cdp_target_url
    
    data = request.get_json() or {}
    target_id = data.get("target_id")
    
    if not cdp_browser_ws:
        return jsonify({"success": False, "error": "未连接到浏览器"})
    
    targets = cdp_get_targets(cdp_browser_ws)
    target = None
    for t in targets:
        if t.get("id") == target_id:
            target = t
            break
    
    if not target:
        return jsonify({"success": False, "error": "找不到指定的目标页面"})
    
    ws_debugger_url = target.get("webSocketDebuggerUrl", "")
    if ws_debugger_url:
        cdp_target_url = ws_debugger_url.replace("ws://", "").replace("wss://", "")
    else:
        cdp_target_url = cdp_browser_ws
    
    return jsonify({
        "success": True,
        "target": {
            "id": target.get("id"),
            "title": target.get("title"),
            "url": target.get("url")
        }
    })

@app.route("/api/cdp/get-cookies", methods=["POST"])
def cdp_fetch_cookies():
    """从指定标签页获取 Cookie（仅从该标签页获取，不跨标签页）"""
    global cdp_browser_ws
    
    data = request.get_json() or {}
    target_id = data.get("target_id")  # 可选：指定标签页 ID
    domain = data.get("domain", "")      # 可选：域名过滤
    
    if not cdp_browser_ws:
        return jsonify({
            "success": False,
            "error": "请先连接浏览器",
            "hint": "点击「连接浏览器」按钮"
        })
    
    targets = cdp_get_targets(cdp_browser_ws)
    if not targets:
        return jsonify({"success": False, "error": "无法获取浏览器标签页列表"})
    
    # 如果指定了 target_id，只从该标签页获取
    if target_id:
        target = None
        for t in targets:
            if t.get("id") == target_id:
                target = t
                break
        
        if not target:
            return jsonify({"success": False, "error": "找不到指定的标签页"})
        
        ws_url = target.get("webSocketDebuggerUrl", "")
        if not ws_url:
            return jsonify({"success": False, "error": "该标签页不支持获取 Cookie"})
        
        ws_url = ws_url.replace("ws://", "").replace("wss://", "")
        
        # 如果提供了域名，只返回匹配该域名的 cookie
        if domain:
            result = cdp_get_cookies(ws_url, domain)
        else:
            # 返回所有 cookie
            result = cdp_get_cookies(ws_url, "")
        
        if result.get("success"):
            cookies = result.get("cookies", [])
            cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
            return jsonify({
                "success": True,
                "cookies": cookie_str,
                "count": len(cookies),
                "raw_cookies": cookies
            })
        else:
            return jsonify({
                "success": False,
                "error": f"在标签页中未找到 {domain} 的 Cookie",
                "hint": "请确保该标签页已打开并登录对应网站"
            })
    
    # 如果没有指定 target_id，返回所有可用标签页信息（让前端选择）
    available = []
    for t in targets:
        ws_url = t.get("webSocketDebuggerUrl", "")
        if not ws_url:
            continue
        available.append({
            "id": t.get("id"),
            "title": t.get("title"),
            "url": t.get("url")
        })
    
    return jsonify({
        "success": False,
        "error": "需要指定标签页",
        "available_targets": available,
        "hint": "请先选择一个标签页"
    })

@app.route("/api/cdp/get-page-info", methods=["POST"])
def cdp_get_page_info():
    """从标签页页面内容中提取信息（如套餐截止日期）"""
    global cdp_browser_ws
    
    data = request.get_json() or {}
    target_id = data.get("target_id")
    service_id = data.get("service_id")  # 用于判断提取什么信息
    
    if not cdp_browser_ws:
        return jsonify({"success": False, "error": "请先连接浏览器"})
    
    targets = cdp_get_targets(cdp_browser_ws)
    target = None
    for t in targets:
        if t.get("id") == target_id:
            target = t
            break
    
    if not target:
        return jsonify({"success": False, "error": "找不到指定的标签页"})
    
    ws_url = target.get("webSocketDebuggerUrl", "").replace("ws://", "").replace("wss://", "")
    
    # 根据 service_id 返回不同的提取脚本
    if service_id == "minimax":
        # MiniMax 页面：从文本中匹配截止日期
        js = """
        (function() {
            var text = document.body.innerText;
            // 匹配 截止日期：MM/DD/YYYY 或 DD/MM/YYYY 等格式
            var match = text.match(/截止日期[：:]\\s*(\\d{1,2}[\\/\\-]\\d{1,2}[\\/\\-]\\d{2,4})/);
            if (match) {
                return match[1];
            }
            return null;
        })()
        """
    elif service_id == "xfyun":
        # 讯飞页面：类似处理
        js = """
        (function() {
            var text = document.body.innerText;
            var match = text.match(/到期[：:]\\s*(\\d{4}[\\/\\-]\\d{1,2}[\\/\\-]\\d{1,2})/);
            if (match) {
                return match[1];
            }
            return null;
        })()
        """
    else:
        return jsonify({"success": False, "error": f"未知服务: {service_id}"})
    
    result = cdp_execute_js(ws_url, js)
    
    if result.get("success"):
        page_value = result.get("result", {}).get("value")
        return jsonify({
            "success": True,
            "page_info": page_value
        })
    else:
        return jsonify({"success": False, "error": result.get("error", "提取失败")})

@app.route("/api/cdp/disconnect", methods=["POST"])
def cdp_disconnect():
    """断开 CDP 连接"""
    global cdp_browser_ws, cdp_target_url
    
    cdp_browser_ws = None
    cdp_target_url = None
    
    return jsonify({"success": True, "message": "已断开连接"})

@app.route("/api/cdp/services")
def cdp_services():
    """获取支持的服务列表"""
    return jsonify({
        "success": True,
        "services": CDP_SERVICES
    })

@app.teardown_appcontext
def cleanup(exception=None):
    pass

if __name__ == "__main__":
    print("🚀 Token Monitor 启动中... http://0.0.0.0:5188")
    print(f"📝 支持的服务: {', '.join(p['name'] for p in USAGE_PLUGINS.values())}")
    print("📝 示例: curl -X POST http://localhost:5188/api/login/refresh -d '{\"service\":\"minimax\"}'")
    app.run(host="0.0.0.0", port=5188, debug=True)
