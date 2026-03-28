# Token Monitor ✨

> 监控 MiniMax 和讯飞星辰 API 用量

## 项目结构

```
~/share/new/
├── backend/           # Flask API 服务
│   └── app.py         # 后端主程序
├── frontend/          # Web 前端静态页面
│   ├── index.html     # 主页面
│   ├── api.html       # API 监控页面
│   └── setup.html     # Cookie 设置页面
├── mobile-app/        # Android 手机端 (Capacitor)
│   ├── src/           # 前端源码
│   └── android/       # Android 原生项目
├── data/              # 数据存储（Cookie 等）
│   ├── minimax_cookies.json
│   └── xfyun_cookies.json
└── README.md
```

## 功能特性

- ✅ MiniMax Token Plan 用量监控
- ✅ 讯飞星辰每日额度监控
- ✅ Web 端 + Android 手机端
- ✅ 内嵌 WebView 自动提取 Cookie
- ✅ CDP 自动获取 Cookie（Web 端）
- ✅ 重置时间倒计时

## 部署架构

```
                    ┌─────────────────┐
                    │   用户浏览器     │
                    │  (Web / 手机)   │
                    └────────┬────────┘
                             │ HTTP
                             ▼
┌─────────────┐     ┌─────────────────┐
│   Nginx     │────►│   Flask API     │
│  (静态资源) │     │   :5188         │
└─────────────┘     └────────┬────────┘
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
            MiniMax API           讯飞 API
```

## 快速启动

### 后端
```bash
cd backend
pip install -r requirements.txt
python3 app.py
```

### Web 前端
直接用浏览器打开 `frontend/index.html`，或者部署到 Nginx。

### Android 手机端
```bash
cd mobile-app
npm install
npm run build
npx cap sync android
cd android && ./gradlew assembleDebug
# APK: android/app/build/outputs/apk/debug/app-debug.apk
```

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/status` | GET | 获取所有服务状态 |
| `/api/minimax` | GET | 获取 MiniMax 用量 |
| `/api/xfyun` | GET | 获取讯飞用量 |
| `/api/set-cookie` | POST | 设置 Cookie |
| `/api/login/status` | GET | 检查登录状态 |

## Cookie 管理

Cookie 存储在 `data/` 目录下：
- `data/minimax_cookies.json`
- `data/xfyun_cookies.json`

**注意**：`data/` 目录已被 `.gitignore` 忽略，Cookie 不会提交到 git。

### 手动设置 Cookie

```bash
# MiniMax
curl -X POST http://localhost:5188/api/set-cookie \
  -H "Content-Type: application/json" \
  -d '{"service":"minimax","cookies":"你的cookie"}'

# 讯飞
curl -X POST http://localhost:5188/api/set-cookie \
  -H "Content-Type: application/json" \
  -d '{"service":"xfyun","cookies":"你的cookie"}'
```

## 数据格式

### MiniMax 返回格式
```json
{
  "page_info": {
    "used": 0,
    "total": 600,
    "percent": 0.0,
    "expiresAt": "2026-03-29 10:00",
    "resetHours": 4,
    "resetMinutes": 32
  }
}
```

### 讯飞返回格式
```json
{
  "page_info": {
    "dailyQuota": 5000.0,
    "dailyUsed": 3943.8,
    "dailyRemain": 1056.2,
    "expiresAt": "2026-04-19 16:10:58"
  }
}
```

## 依赖

### 后端
```
Flask>=3.0.0
requests>=2.31.0
```

### 手机端
```
@capacitor/core: ^8.0.0
@capacitor/android: ^8.0.0
vite: ^8.0.0
```

## 安全说明

- Cookie 存储在 `data/` 目录，已被 `.gitignore` 忽略
- 日志文件 `*.log` 已被 `.gitignore` 忽略
- 无硬编码的敏感信息（API Key、密码等）
- 所有敏感数据仅存储在本地

## 开发规范

### Git 提交格式
```bash
git commit -m "feat: 新功能描述
- 具体改动1
- 具体改动2

fix: 修复描述
- 修复内容"
```

### 推送前检查
1. 确认无敏感信息泄露（Cookie、API Key、密码等）
2. 确认 `data/*.json` 已被 `.gitignore` 忽略
3. 确认 `*.log` 已被 `.gitignore` 忽略

### 推送命令
```bash
git push origin master
```

---

*由爱丽丝维护 ✨*
