# Token Monitor ✨

> 监控 MiniMax 和讯飞星辰 API 用量

## 🚀 快速启动

**前提**：Python 3.10+ 已安装、**MySQL 8.0+ 已安装且服务已启动**。

**Windows (PowerShell)**：
```powershell
cd backend
$env:INIT_MYSQL_ADMIN_PASSWORD = '你的MySQL密码'; .\init_env.ps1
.\start.bat
```

**Linux / WSL / macOS**：
```bash
cd backend
INIT_MYSQL_ADMIN_PASSWORD='你的MySQL密码' ./init_env.sh
./start.sh
```

启动后打开 **`http://localhost:<PORT>`** 即可（`<PORT>` 以 `backend/.env` 里 `PORT` 为准，默认 **5188**）。

详细步骤见 **[DEPLOYMENT.md](./DEPLOYMENT.md)**。完整运维手册仅在本地 **`docs/OPERATIONS.md`**（`docs/` 不入库，见 DEPLOYMENT 顶部说明）。

## 项目结构

```
~/share/new/
├── backend/           # FastAPI 后端
│   ├── app.py         # 应用入口
│   └── .env.example   # 环境变量模板
├── docs/              # （可选，本地维护，不入库）OPERATIONS、ARCHITECTURE 等
├── frontend/          # Web 前端静态页面
│   ├── js/            # 共享脚本（监控页 / 多页复用）
│   │   ├── api-dashboard-state.js   # window.TMD（页面 ID、API_BASE）
│   │   ├── api-dashboard-core.js    # window.TMDCore（escapeHtml、指标、小折线图 SVG 等）
│   │   ├── api-dashboard-app.js     # window.TMDApp（api.html 看板逻辑）
│   │   └── ui-shared.js             # window.TMDUi（Toast、顶栏链接、自定义 <select>；accounts/admin）
│   ├── index.html     # 入口
│   ├── login.html     # 登录
│   ├── api.html       # 实时监控看板
│   ├── history.html   # 历史用量趋势（ECharts）
│   ├── accounts.html  # 账号与告警管理
│   ├── admin.html     # 管理后台（邀请码、API Key）
│   └── setup.html     # 凭证 / CDP 设置
├── mobile-app/        # Android 手机端 (Capacitor + Vite)
│   ├── src/           # 移动端 H5 源码（构建产物进 www/）
│   ├── www/           # vite build 输出（由 cap sync 拷入 android）
│   └── android/       # Android Gradle 工程
├── data/              # 数据存储（Cookie 等）
│   ├── minimax_cookies.json
│   └── xfyun_cookies.json
└── README.md
```

## 功能特性

- ✅ MiniMax Token Plan 用量监控
- ✅ 讯飞星辰每日额度监控
- ✅ Web 端 + Android 手机端
- ✅ **历史用量趋势**（`history.html`，24h/7d，ECharts 双轴）
- ✅ 多用户登录、账号与告警管理、API Key / 邀请码（管理端）
- ✅ 账号列表 / 告警规则 / 管理后台 API 密钥等列表 **每页 5 条分页**；监控页「最近告警」固定约 **3 条可视高度 + 自动滚动**
- ✅ 监控卡「最近 7 天使用率」小折线图（MiniMax / 讯飞配色区分；渐变填充 + 柔光描边；纵轴按数据区间自适应）
- ✅ 卡片为纯色半透明背景（**无 backdrop-filter 毛玻璃、无悬停上浮**），减少视觉干扰
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
│   Nginx     │────►│   FastAPI API   │
│  (静态资源) │     │     :5188       │
└─────────────┘     └────────┬────────┘
                               │
              ┌───────────────┴───────────────┐
              ▼                               ▼
      MiniMax API                    更多 AI 服务商...
      讯飞 API                    （通过服务注册表动态接入）
```

## 快速启动（本地开发）

完整步骤与密钥配置见 **[DEPLOYMENT.md](./DEPLOYMENT.md)**。

### 后端（需已配置 `backend/.env` 与 MySQL）

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate   # Windows 用 .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 5188
```

### Web 前端

开发时访问后端挂载的静态页（默认与 backend 同级的 `frontend/`，根路径由 `app.py` 挂载）。也可将 `frontend/` 交给 Nginx 单独托管并反向代理 API。

**脚本依赖（重要）**：`api.html` 顺序为 `api-dashboard-state.js` → `api-dashboard-core.js` → `api-dashboard-app.js`。`accounts.html` / `admin.html` 在 State/Core 之后加载 **`js/ui-shared.js`**（`window.TMDUi`），再执行页内脚本。详见各文件头注释。

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
| `/auth/api-keys` | POST | 创建 API Key（仅返回一次明文） |
| `/auth/api-keys` | GET | 列出 API Key（不返回明文） |
| `/auth/api-keys/{id}` | DELETE | 撤销 API Key |
| `/auth/api-keys/{id}/rotate` | POST | 轮换 API Key（返回新明文） |

## API Key 鉴权

API 支持两种并行鉴权方式：

- **JWT 用户会话**：适合浏览器端登录态（`Authorization: Bearer <token>`）
- **API Key 程序调用**：适合脚本、CI、服务间调用（`X-API-Key: tmk_xxx`）

权限说明：普通用户只能管理自己的 Key，管理员可管理全部用户的 Key。

### 使用示例

```bash
# 使用 API Key 访问受保护接口
curl "http://localhost:5188/api/current-cookies" \
  -H "X-API-Key: tmk_xxx"

# 也支持 Authorization: ApiKey 形式
curl "http://localhost:5188/api/current-cookies" \
  -H "Authorization: ApiKey tmk_xxx"
```

### Scope 权限说明

- `cookie:read`：读取 Cookie 相关信息（如 `/api/current-cookies`、`/api/cdp/targets`）
- `cookie:write`：写入/变更 Cookie 或连接状态（如 `/api/cookie/set`、`/api/clear-cache`、`/api/cdp/connect`）
- `*`：通配符，表示拥有全部 scope（仅建议在受控场景使用）

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
见 **`backend/requirements.txt`**（FastAPI、SQLAlchemy、MySQL 异步驱动、JWT 等）。

### 手机端
```
@capacitor/core: ^8.0.0
@capacitor/android: ^8.0.0
vite: ^8.0.0
```

## 安全说明

- Cookie 与加密数据依赖 **`backend/.env`** 中的 `APP_SECRET_KEY` 等，**勿提交** `.env`。
- 业务 Cookie 加密存库；本地 `data/` 与日志已按 `.gitignore` 忽略（以仓库实际规则为准）。
- 生产密钥与数据库口令**按环境独立生成**，见 **[DEPLOYMENT.md](./DEPLOYMENT.md)**。

## 开发规范

协作规范、UI 一致性、依赖安全基线、**Git/proxychains 推送**等见**本地**维护的 **`docs/开发规范.md`**（该目录与根目录 **`TODO.md`** 已被 **`.gitignore` 排除，不得推送至远端**；克隆仓库后按需自建）。可选：在仓库根执行 **`git config core.hooksPath scripts/git-hooks`**，用钩子防止误将 `docs/`、`TODO.md` 提交进 Git，说明见 **`scripts/git-hooks/README`**。

以下为 Git 习惯摘要（针对**允许入库**的文件）。

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
git push origin <分支名>
```

若 Agent/终端由 `proxychains4` 启动，子进程会继承 `LD_PRELOAD`，可能导致 `git push` **无法解析 github.com**。应临时去掉预加载：

```bash
env -u LD_PRELOAD git push origin <分支名>
# 或：LD_PRELOAD= git push origin <分支名>
```

详见 **`docs/开发规范.md`**（仓库内 `docs/开发规范.md` 与根目录说明一致）「提交流程检查清单 → Git 远程推送」。

---

*由爱丽丝维护 ✨*

---

## 构建说明

### 1. 环境要求

| 软件 | 版本 | 说明 |
|------|------|------|
| JDK / JBR | 17+ | Android Studio 自带 JBR 或独立安装 |
| Android SDK | - | Android Studio 安装时一并安装 |
| Node.js | 18+ | 手机端构建需要 |

### 2. Android 构建配置

首次构建前创建 `mobile-app/android/local.properties`，`sdk.dir` 指向本机 **Android SDK 根目录**（不要用引号）：

**Windows（Android Studio 默认）：**
```properties
sdk.dir=C\:\\Users\\你的用户名\\AppData\\Local\\Android\\Sdk
```

**Linux / WSL（SDK 在 Linux 文件系统时）：**
```properties
sdk.dir=/home/你的用户/android-sdk
```

### 3. 构建命令

```bash
cd mobile-app

# 安装依赖
npm install

# 构建 Web 资源
npm run build

# 同步到 Android
npx cap sync android

# 用 Android Studio 打开并构建
npx cap open android
```

**或命令行（macOS / Linux / WSL）：**
```bash
cd mobile-app/android
./gradlew assembleDebug
# 输出：app/build/outputs/apk/debug/app-debug.apk
```

**Windows `cmd.exe`：** `cd android` 后使用 `gradlew.bat assembleDebug`。

仅改 H5 后若 APK 里页面未更新，可再执行 `./gradlew :app:clean :app:assembleDebug` 强制重打资源。

**安装到已连接模拟器/真机：**
```bash
# 示例：SDK platform-tools 已在 PATH
adb install -r mobile-app/android/app/build/outputs/apk/debug/app-debug.apk
```

### 4. 常见问题

**Q: 提示 `BUILD TOOLS 损坏`？**
A: 删除 `build-tools` 问题版本，重新安装 Android SDK Build Tools

**Q: Gradle 下载超时？**
A: 设置代理或使用国内镜像

**Q: 提示 `JAVA_HOME` 未设置？**
A: 设置环境变量指向 JDK/JBR 目录

---

*其他问题可提交 Issue*
