# Token Monitor ✨

> 监控 MiniMax 和讯飞星辰 API 用量

## 🚀 快速启动

**前提**：Python 3.10+、**MySQL 8.0+** 已安装且服务已启动。

**Windows (PowerShell)**：
```powershell
cd backend
$env:INIT_MYSQL_ADMIN_USER='你的高权限用户名' INIT_MYSQL_ADMIN_PASSWORD='该用户的密码' .\init_env.ps1
.\start.bat
```

**Linux / WSL / macOS**：
```bash
cd backend
INIT_MYSQL_ADMIN_USER='你的高权限用户名' INIT_MYSQL_ADMIN_PASSWORD='该用户的密码' ./init_env.sh
./start.sh
```

启动后打开 **`http://localhost:<PORT>`**（端口以 `backend/.env` 中 `PORT` 为准，默认 **5188**）。

详细步骤与生产部署见 **[DEPLOYMENT.md](./DEPLOYMENT.md)**。

## 项目结构

```
~/share/new/
├── backend/           # FastAPI 后端
│   ├── app.py         # 应用入口
│   └── .env.example   # 环境变量模板
├── frontend/          # Web 前端静态页面
│   ├── js/            # 共享脚本（监控页 / 多页复用）
│   │   ├── api-dashboard-state.js   # window.TMD（页面 ID、API_BASE）
│   │   ├── api-dashboard-core.js    # window.TMDCore（escapeHtml、指标、小折线图 SVG 等）
│   │   ├── api-dashboard-app.js     # window.TMDApp（api.html 看板逻辑）
│   │   └── ui-shared.js             # window.TMDUi（Toast、顶栏链接、自定义 <select>；accounts/admin）
│   ├── public/        # 静态资源（含 favicon 等）
│   ├── icons/         # 生成站标（源图 svg/plasma → webp/ico；移动端 launcher 用 design-preview）
│   ├── index.html     # 入口
│   ├── login.html     # 登录
│   ├── api.html       # 实时监控看板
│   ├── history.html   # 历史用量趋势（ECharts）
│   ├── accounts.html  # 账号与告警管理
│   ├── admin.html     # 管理后台（平台用户、邀请码、API Key 等）
│   └── setup.html     # 凭证 / CDP 设置
├── mobile-app/        # Android 手机端 (Capacitor + Vite)
│   ├── src/           # 移动端 H5 源码（构建产物进 www/）
│   ├── www/           # vite build 输出（由 cap sync 拷入 android）
│   ├── public/        # Vite public 资源（构建复制到 www）
│   ├── design-preview/# 移动端欢迎页/图标等设计源图（prepare_launcher_icons.py）
│   ├── pack.sh        # 一键：npm install → build → cap sync → assembleDebug（输出 debug APK）
│   └── android/       # Android Gradle 工程
└── README.md
```

## 功能特性

- MiniMax Token Plan 与讯飞星辰每日额度监控（Web + Android）
- **历史用量趋势**（`history.html`，24h/7d，ECharts）
- 多用户、账号与告警规则；管理端 **平台用户**（角色/启用/删除等，超级管理员与普通管理员权限不同）、**邀请码**、**API Key**；列表分页与监控页「最近告警」展示
- 监控卡「最近 7 天使用率」小折线图；卡片为纯色半透明（无毛玻璃与悬停上浮）
- WebView / CDP 提取 Cookie；重置时间倒计时

## 部署架构

```
                    ┌─────────────────┐
                    │   用户浏览器     │
                    │  (Web / 手机)   │
                    └────────┬────────┘
                             │ HTTP
                             ▼
┌─────────────┐     ┌─────────────────┐
│   Nginx     │────►│   FastAPI API   │
│  (静态资源) │     │     :5188       │
└─────────────┘     └────────┬────────┘
                               │
              ┌───────────────┴───────────────┐
              ▼                               ▼
      MiniMax API                    更多服务商…
      讯飞 API                    （服务注册表动态接入）
```

## 本地开发

环境与密钥见 **[DEPLOYMENT.md](./DEPLOYMENT.md)**。

### 后端（需已配置 `backend/.env` 与 MySQL）

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 5188
```

### Web 前端

由后端挂载同级 `frontend/`（见 `backend/app.py` 中 `FRONTEND_DIR`），或将静态页交给 Nginx 并反向代理 API。

**脚本顺序**：`api.html` 为 `api-dashboard-state.js` → `core` → `app`；`accounts.html` / `admin.html` 在 State/Core 后加载 `js/ui-shared.js`，再执行页内脚本。

### Android

工程在 **`mobile-app/`**（Capacitor + Vite）。**环境、`local.properties`、新环境前置条件、一键 `pack.sh`、分步命令与排障** 都写在下文 **「构建说明（Android）」** 里，此处不重复。

已在本机配好 **Node / JDK / Android SDK** 时，可直接进入 `mobile-app/` 执行 **`./pack.sh`** 打出 debug APK；**首次或新机器**请先阅读该节的 **「前置条件」**。


## Cookie 与账号数据

- 业务 Cookie **仅存 MySQL**（`/api/accounts` 等，`cookies_encrypted` 字段）；设置页、看板等均走账号接口。
- CDP 等仅把 Cookie **提交到后端写入库**，不再使用项目根 `data/*.json`（该路径已移除）。

## 数据格式（业务字段摘要）

### MiniMax（`page_info` 片段）

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

### 讯飞（`page_info` 片段；单位与上游额度字段一致，见采集服务实现）

```json
{
  "page_info": {
    "used": 394.38,
    "total": 500.0,
    "remain": 105.62,
    "percent": 78.9,
    "expiresAt": "2026-04-19 16:10:58",
    "resetHours": 0,
    "resetMinutes": 0,
    "resetCaption": "每日 00:00"
  }
}
```

## 依赖

- **后端**：见 `backend/requirements.txt`
- **手机端**：`@capacitor/core` / `@capacitor/android` **^8.3.0**，`vite` **^8.0.3**（以 `mobile-app/package.json` 为准）

## 安全说明

- 密钥与 **`backend/.env`** 勿提交；生产按环境独立配置见 **DEPLOYMENT.md**。
- Cookie 加密存库；日志与本地敏感文件以仓库 `.gitignore` 为准。

## 开发规范

**通用准则**见 **`docs/开发规范.md`**（跨项目可复用的协作、UI/接口约定、Git 推送与验证习惯）。**本仓库依赖版本底线**见 **`docs/SECURITY.md`**。若根目录 **`.gitignore`** 排除了 `docs/`，以你本地副本为准；勿将敏感笔记提交远端。可选：`git config core.hooksPath scripts/git-hooks`（说明见 `scripts/git-hooks/README`）。

---

*由爱丽丝维护 ✨*

---

## 构建说明（Android）

### 首次构建

1. 创建 `mobile-app/android/local.properties`，写入 SDK 路径：

```properties
# Windows 示例
sdk.dir=C\:\\Users\\用户名\\AppData\\Local\\Android\\Sdk

# Linux / WSL 示例
# sdk.dir=/home/用户名/android-sdk
```

2. 建议在 Android Studio 中打开 `mobile-app/android/`，由 IDE 自动补全 Platform / Build-Tools 等组件。

### 前置条件

| 依赖 | 版本要求 |
|------|---------|
| Node.js | 18+（含 npm） |
| JDK / JBR | 17+ |
| Android SDK | 已装且含工程所需 Platform / Build-Tools |
| bash | Windows 推荐 WSL 或 Git Bash |

### 一键打包

```bash
cd mobile-app
chmod +x pack.sh android/gradlew   # 首次可能需要
./pack.sh
```

**产物：** `mobile-app/android/app/build/outputs/apk/debug/app-debug.apk`

### 分步构建

```bash
cd mobile-app
npm install && npm run build && npx cap sync android
cd android && ./gradlew assembleDebug
# Windows: gradlew.bat assembleDebug
```

### 常见问题

| 问题 | 解决 |
|------|------|
| Build Tools 损坏 | 重装对应版本 |
| Gradle 下载超时 | 配置代理或镜像 |
| `JAVA_HOME` 未找到 | 指向 JDK 根目录（非 bin） |

---

*其他问题可提交 Issue*
