# Token Monitor 部署指南

面向**全新环境**的部署流程。配置项说明见 `backend/.env.example`。

---

## 🚀 快速启动（一键部署）

**前提**：Python 3.10+ 已安装、**MySQL 8.0+ 已安装且服务已启动**。

### Windows（PowerShell）

```powershell
cd backend
# 初始化（生成密钥 + 自动建库，需 MySQL 管理员密码）
$env:INIT_MYSQL_ADMIN_PASSWORD = '你的MySQL密码'; .\init_env.ps1
# 启动
.\start.bat
```

### Linux / WSL / macOS

```bash
cd backend
# 初始化（生成密钥 + 自动建库，需 MySQL 管理员密码）
INIT_MYSQL_ADMIN_PASSWORD='你的MySQL密码' ./init_env.sh
# 启动
./start.sh
```

> 启动成功后打开浏览器访问 **http://localhost:5188**，首次打开会自动引导创建管理员账号。

---

*下面各章节为详细说明，无需立即阅读。*

---

## 📋 快速开始（5 步完成）

| 步骤 | 操作 |
|------|------|
| 0 | **MySQL 管理员账户**：先设置好 root（或管理员）密码 |
| 1 | 安装 Python 3.10+ 和 MySQL 5.7+（推荐 8.0+），MySQL 已启动 |
| 2 | `cd backend && pip install -r requirements.txt` |
| 3 | 运行初始化脚本（见下方），生成密钥和 `.env` |
| 4 | 启动：`./start.sh`（Unix）或 `.\start.bat`（Windows） |
| 5 | 打开浏览器访问 `http://localhost:5188`，首次引导创建管理员账号 |

---

## 数据库迁移（API Key）

在升级到包含 API Key 鉴权的版本后，请执行一次迁移脚本：

```bash
cd backend
python3 -m utils.migrate_api_keys
```

---

## 迁移脚本说明

当前版本常用迁移脚本（建议在 `backend/` 目录按顺序执行）：

```bash
cd backend
python3 -m utils.migrate_service_registry
python3 -m utils.migrate_alerting_p2_3
python3 -m utils.migrate_api_keys
```

- `migrate_service_registry`：服务注册表扩展 + `usage_snapshots` 表与索引
- `migrate_alerting_p2_3`：告警字段扩展 + `alert_events` 表与索引
- `migrate_api_keys`：`api_keys` 表与索引

> 上述脚本按可重复执行设计，重复运行不会破坏现有结构。

---

## 配置项总览

完整字段以 `backend/.env.example` 为准，发布前至少确认：

- 安全密钥：`JWT_SECRET_KEY`、`APP_SECRET_KEY`
- 数据库连接：`DB_HOST`、`DB_PORT`、`DB_NAME`、`DB_USER`、`DB_PASSWORD`
- 服务启动：`HOST`、`PORT`、`DEBUG`
- 自动采集：`AUTO_COLLECT_ENABLED`、`AUTO_COLLECT_INTERVAL_SECONDS`、`AUTO_COLLECT_MAX_CONCURRENCY`、`AUTO_COLLECT_RETRY_ATTEMPTS`、`AUTO_COLLECT_RETRY_DELAY_SECONDS`
- 告警评估：`ALERT_EVAL_ENABLED`、`ALERT_DEFAULT_THRESHOLD`、`ALERT_DEFAULT_COOLDOWN_SECONDS`

---

## 初始化脚本详解

> ⚠️ **前提**：MySQL 管理员账户（如 root）已有密码。

**脚本不会覆盖已存在的 `.env`。**

| 操作 | Unix | Windows |
|------|------|---------|
| 查看帮助 | `./init_env.sh --help` | `.\init_env.ps1 -Help` |
| 仅生成密钥（不建库） | `./init_env.sh --skip-mysql` | `.\init_env.ps1 -SkipMySql` |
| 生成密钥 + 自动建库 | `INIT_MYSQL_ADMIN_PASSWORD='密码' ./init_env.sh` | `$env:INIT_MYSQL_ADMIN_PASSWORD = "密码"; .\init_env.ps1` |

### 手工建库（不用脚本时）

```sql
CREATE DATABASE IF NOT EXISTS token_monitor CHARACTER SET utf8mb4;
CREATE USER IF NOT EXISTS 'tm_user'@'localhost' IDENTIFIED BY '你的密码';
GRANT ALL ON token_monitor.* TO 'tm_user'@'localhost';
FLUSH PRIVILEGES;
```

---

## 常见问题

| 问题 | 解决 |
|------|------|
| `.env 已存在` | 脚本保护；删掉 `backend/.env` 重来，或手动编辑 |
| `ValidationError` | 检查 `.env` 必填项是否完整 |
| `Access denied` | 确认 MySQL 密码与 `DB_PASSWORD` 一致 |
| `Can't connect` | 检查 MySQL 服务、`DB_HOST`、`DB_PORT` |
| 端口占用 | 改 `.env` 中 `PORT`，或 `kill $(lsof -ti:5188)` |

---

## 安全提醒

- **不要提交** `backend/.env` 到 Git
- 生产环境关闭 `DEBUG`，使用 HTTPS
- 轮换 `JWT_SECRET_KEY` 会使所有已登录用户失效

---

## API Key 使用

### 管理后台创建

1. 管理员登录 `admin.html`
2. 「API Key 管理」区域填写名称、Scope、可选过期时间
3. 点击创建并**立即复制明文**（只显示一次）

### 程序调用

```bash
# 方式一：X-API-Key 头（推荐）
curl "http://localhost:5188/api/current-cookies" -H "X-API-Key: tmk_xxx"

# 方式二：Authorization: ApiKey 头
curl "http://localhost:5188/api/current-cookies" -H "Authorization: ApiKey tmk_xxx"
```

常用 Scope：`cookie:read`（读取）、`cookie:write`（写入/变更）

---

*更多说明见 [README.md](./README.md)。*
