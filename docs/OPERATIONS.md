# Token Monitor 运维手册

> **单一入口**：一键部署、迁移、配置、日常命令、发布回归（合并原 `DEPLOYMENT.md`、`MIGRATION_GUIDE.md`、`RUNBOOK.md`、`CONFIG_MANUAL.md`、`REGRESSION_CHECKLIST.md`）。
>
> 文中 `curl` 示例主机端口以 **`127.0.0.1:5188`** 为例；实际请替换为 `backend/.env` 中的 `PORT`。

---

## 目录

1. [快速启动（一键）](#1-快速启动一键)
2. [全新环境五步走](#2-全新环境五步走)
3. [数据库迁移脚本](#3-数据库迁移脚本)
4. [环境变量（完整表）](#4-环境变量完整表)
5. [推荐配置、调优与安全](#5-推荐配置调优与安全)
6. [日常命令（Runbook）](#6-日常命令runbook)
7. [初始化脚本与手工建库](#7-初始化脚本与手工建库)
8. [常见问题 / 安全 / API Key](#8-常见问题--安全--api-key)
9. [升级验证](#9-升级验证)
10. [发布回归 Checklist](#10-发布回归-checklist)

---

## 1. 快速启动（一键）

**前提**：Python 3.10+、**MySQL 8.0+** 已安装且服务已启动。

### Windows（PowerShell）

```powershell
cd backend
$env:INIT_MYSQL_ADMIN_PASSWORD = '你的MySQL密码'; .\init_env.ps1
.\start.bat
```

### Linux / WSL / macOS

```bash
cd backend
INIT_MYSQL_ADMIN_PASSWORD='你的MySQL密码' ./init_env.sh
./start.sh
```

浏览器访问 `http://localhost:<PORT>`（`<PORT>` 见 `backend/.env`，默认 5188）。首次访问引导创建管理员。

---

## 2. 全新环境五步走

| 步骤 | 操作 |
|------|------|
| 0 | MySQL 管理员账户（如 root）已设密码 |
| 1 | 安装 Python 3.10+、MySQL 8.0+，MySQL 已启动 |
| 2 | `cd backend && pip install -r requirements.txt` |
| 3 | 运行 `init_env.sh` / `init_env.ps1`（见 §7），生成 `backend/.env` |
| 4 | `./start.sh` 或 `.\start.bat` |
| 5 | 浏览器访问、`§3` 迁移按需执行 |

---

## 3. 数据库迁移脚本

在 `backend/` 目录**建议按顺序**执行（可重复执行）：

```bash
cd backend
python3 -m utils.migrate_service_registry
python3 -m utils.migrate_alerting_p2_3
python3 -m utils.migrate_api_keys
```

| 模块 | 作用 |
|------|------|
| `migrate_service_registry` | 服务注册表扩展 + `usage_snapshots` 表与索引 |
| `migrate_alerting_p2_3` | 告警字段扩展 + `alert_events` 表与索引 |
| `migrate_api_keys` | `api_keys` 表与索引 |

仅升级到含 API Key 的版本时，至少执行 `migrate_api_keys`。

---

## 4. 环境变量（完整表）

来源：`backend/core/config.py` 与 `backend/.env.example`。

- 默认从 `backend/.env` 读取（UTF-8）；支持环境变量覆盖；未识别字段忽略（`extra="ignore"`）。

| 配置项 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `API_KEY` | 否 | 空 | 预留 |
| `APP_SECRET_KEY` | 是 | 无 | Cookie 等加密，建议 32+ 随机串 |
| `JWT_SECRET_KEY` | 是 | 无 | JWT 签名，建议 32+ 随机串 |
| `JWT_ALGORITHM` | 否 | `HS256` | JWT 算法 |
| `JWT_EXPIRE_MINUTES` | 否 | `10080` | JWT 过期（分钟，默认 7 天） |
| `HOST` | 否 | `0.0.0.0` | 监听地址 |
| `PORT` | 否 | `5188` | 监听端口 |
| `DEBUG` | 否 | `false` | 调试模式 |
| `DB_HOST` | 是 | `localhost` | MySQL 地址 |
| `DB_PORT` | 是 | `3306` | MySQL 端口 |
| `DB_NAME` | 是 | `token_monitor` | 数据库名 |
| `DB_USER` | 是 | `tm_user` | 数据库用户 |
| `DB_PASSWORD` | 是 | 无 | 数据库密码 |
| `COOKIE_DIR` | 否 | `data` | Cookie 文件目录 |
| `CACHE_TTL` | 否 | `60` | 缓存 TTL（秒） |
| `AUTO_COLLECT_ENABLED` | 否 | `true` | 自动采集 |
| `AUTO_COLLECT_INTERVAL_SECONDS` | 否 | `300` | 采集间隔（秒） |
| `AUTO_COLLECT_MAX_CONCURRENCY` | 否 | `3` | 单轮最大并发账号数 |
| `AUTO_COLLECT_RETRY_ATTEMPTS` | 否 | `2` | 单账号尝试次数（含首次） |
| `AUTO_COLLECT_RETRY_DELAY_SECONDS` | 否 | `1.0` | 重试退避（秒） |
| `ALERT_EVAL_ENABLED` | 否 | `true` | 告警评估 |
| `ALERT_DEFAULT_THRESHOLD` | 否 | `80.0` | 默认阈值（%） |
| `ALERT_DEFAULT_COOLDOWN_SECONDS` | 否 | `1800` | 默认冷却（秒） |
| `CDP_HOST` | 否 | 无 | CDP 主机（可选） |
| `CDP_PORT` | 否 | 无 | CDP 端口（可选） |

---

## 5. 推荐配置、调优与安全

### 5.1 生产 env 示例

```env
JWT_SECRET_KEY=<32+随机串>
APP_SECRET_KEY=<32+随机串>
DB_HOST=localhost
DB_PORT=3306
DB_NAME=token_monitor
DB_USER=tm_user
DB_PASSWORD=<强密码>
HOST=0.0.0.0
PORT=5188
DEBUG=false
COOKIE_DIR=data
CACHE_TTL=60
AUTO_COLLECT_ENABLED=true
AUTO_COLLECT_INTERVAL_SECONDS=300
AUTO_COLLECT_MAX_CONCURRENCY=3
AUTO_COLLECT_RETRY_ATTEMPTS=2
AUTO_COLLECT_RETRY_DELAY_SECONDS=1.0
ALERT_EVAL_ENABLED=true
ALERT_DEFAULT_THRESHOLD=80
ALERT_DEFAULT_COOLDOWN_SECONDS=1800
```

### 5.2 采集 / 告警调优

| 参数 | 生产推荐 | 说明 |
|---|---:|---|
| `AUTO_COLLECT_ENABLED` | `true` | 开启自动采集 |
| `AUTO_COLLECT_INTERVAL_SECONDS` | `300` | 兼顾实时与上游压力 |
| `AUTO_COLLECT_MAX_CONCURRENCY` | `3` | 建议 2~5 |
| `AUTO_COLLECT_RETRY_ATTEMPTS` | `2` | 首尝 + 1 次重试 |
| `AUTO_COLLECT_RETRY_DELAY_SECONDS` | `1.0` | 网络抖动退避 |
| `ALERT_EVAL_ENABLED` | `true` | 告警评估 |
| `ALERT_DEFAULT_THRESHOLD` | `80` | 可按规则 per metric 覆盖 |
| `ALERT_DEFAULT_COOLDOWN_SECONDS` | `1800` | 抑制重复告警 |

- 账号数很多（>200）：先增大 `AUTO_COLLECT_INTERVAL_SECONDS`，再调并发。
- 告警太吵：提高 `ALERT_DEFAULT_COOLDOWN_SECONDS`（如 3600）。
- 采集偶发失败：可将 `AUTO_COLLECT_RETRY_ATTEMPTS` 提到 3。

### 5.3 安全

- 勿提交真实 `backend/.env`。
- 生产关闭 `DEBUG`，优先 HTTPS。
- 轮换 `JWT_SECRET_KEY` 会使已登录用户全部失效。
- 定期轮换 `APP_SECRET_KEY`、`DB_PASSWORD`；数据库账号最小权限。

---

## 6. 日常命令（Runbook）

> 指标键统一为 `used` / `total` / `percent`；示例勿再用旧键 `quota`。

### 启动（开发）

```bash
cd /mnt/d/wsl/share/new/backend
uvicorn app:app --reload --host 0.0.0.0 --port 5188
```

（端口与 `.env` 一致。）

### 健康检查

```bash
curl -s http://127.0.0.1:5188/api/health
```

### 手动同步

```bash
curl -X POST "http://127.0.0.1:5188/api/accounts/<ACCOUNT_ID>/sync" \
  -H "Authorization: Bearer <TOKEN>"
```

### 历史查询（`metric_key` 可选；省略则不过滤）

```bash
curl "http://127.0.0.1:5188/api/accounts/<ACCOUNT_ID>/history?limit=20&offset=0&metric_key=percent&start_at=2026-03-31T00:00:00Z&end_at=2026-03-31T23:59:59Z" \
  -H "Authorization: Bearer <TOKEN>"
```

### 告警规则与事件

```bash
curl -X PUT "http://127.0.0.1:5188/api/accounts/<ACCOUNT_ID>/alerts/percent" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{"threshold":80,"cooldown_seconds":1800,"is_enabled":true,"notify_channels":["log"]}'

curl "http://127.0.0.1:5188/api/accounts/<ACCOUNT_ID>/alerts" \
  -H "Authorization: Bearer <TOKEN>"

curl "http://127.0.0.1:5188/api/accounts/<ACCOUNT_ID>/alerts/events?limit=20&offset=0" \
  -H "Authorization: Bearer <TOKEN>"
```

### 独立测试框架（仓库外）

```bash
cd /mnt/d/wsl/share/test-framework
pytest backend_tests/integration -v
```

---

## 7. 初始化脚本与手工建库

> 前提：MySQL 管理员已有密码。**脚本不会覆盖已存在的 `backend/.env`**。

| 操作 | Unix | Windows |
|------|------|---------|
| 帮助 | `./init_env.sh --help` | `.\init_env.ps1 -Help` |
| 仅密钥（不建库） | `./init_env.sh --skip-mysql` | `.\init_env.ps1 -SkipMySql` |
| 密钥 + 自动建库 | `INIT_MYSQL_ADMIN_PASSWORD='…' ./init_env.sh` | `$env:INIT_MYSQL_ADMIN_PASSWORD="…"; .\init_env.ps1` |

手工建库（不用脚本时）：

```sql
CREATE DATABASE IF NOT EXISTS token_monitor CHARACTER SET utf8mb4;
CREATE USER IF NOT EXISTS 'tm_user'@'localhost' IDENTIFIED BY '你的密码';
GRANT ALL ON token_monitor.* TO 'tm_user'@'localhost';
FLUSH PRIVILEGES;
```

---

## 8. 常见问题 / 安全 / API Key

### 常见问题

| 问题 | 解决 |
|------|------|
| `.env 已存在` | 删 `backend/.env` 重来，或手工编辑 |
| `ValidationError` | 检查 `.env` 必填项 |
| `Access denied` | 核对 MySQL 与 `DB_PASSWORD` |
| `Can't connect` | 查 MySQL 服务、`DB_HOST`、`DB_PORT` |
| 端口占用 | 改 `.env` 的 `PORT` 或结束占用进程 |

### API Key（程序调用）

管理端 `admin.html` 创建后**立即复制明文**（只显示一次）。

```bash
curl "http://127.0.0.1:5188/api/current-cookies" -H "X-API-Key: tmk_xxx"
curl "http://127.0.0.1:5188/api/current-cookies" -H "Authorization: ApiKey tmk_xxx"
```

常用 Scope：`cookie:read`、`cookie:write`。

---

## 9. 升级验证

```bash
curl -s http://127.0.0.1:5188/api/health
```

```bash
curl -s http://127.0.0.1:5188/api/services -H "Authorization: Bearer <TOKEN>"
```

```bash
curl -s "http://127.0.0.1:5188/api/accounts/<ACCOUNT_ID>/history?limit=1&offset=0" \
  -H "Authorization: Bearer <TOKEN>"
```

预期：`source=usage_snapshots`，结构含 `pagination`、`filters`、`items`。

```bash
curl -s "http://127.0.0.1:5188/api/accounts/<ACCOUNT_ID>/alerts" \
  -H "Authorization: Bearer <TOKEN>"
curl -s "http://127.0.0.1:5188/api/accounts/<ACCOUNT_ID>/alerts/events?limit=10&offset=0" \
  -H "Authorization: Bearer <TOKEN>"
```

预期：HTTP 200，无 5xx。

服务启动时会 `init_db`、seed 服务注册表、按配置启动自动采集。

---

## 10. 发布回归 Checklist

> 维护说明（2026-04）：指标键统一 `percent`。`history.html`：双 Y 轴、`metric_key` 可省略。

用途：发布前/后快速回归（采集、历史、告警、筛选、调度、异常）。

### 0) 环境准备

- [ ] 启动后端（端口与 `.env` 一致）
- [ ] 准备 token：`GET /auth/me` 成功
- [ ] 至少 1 个已配置 Cookie 的账号（建议 MiniMax + 讯飞各 1）

### 1) 采集

- [ ] `POST /api/accounts/<ACCOUNT_ID>/sync` → 200，`success=true`，含 `usage`
- [ ] `GET /api/accounts` → `last_sync_at` 更新；失败账号可看 `last_collect_status`

### 2) 历史

- [ ] `GET .../history?limit=20&offset=0` → 含 `source`、`pagination`、`filters`、`items`，`source=usage_snapshots`
- [ ] `items[0]` 含 `metric_key`、`used`、`total`、`percent`、`collected_at`
- [ ] （可选）打开 `history.html`：24h/7d、双 Y 轴、全窗口时间轴、状态栏范围与覆盖率、无单 metric 下拉

### 3) 告警

- [ ] `PUT .../alerts/percent` + `GET .../alerts` → 规则与提交一致
- [ ] `GET .../alerts/events` → 分页 + `status` 为 `triggered`/`recovered`
- [ ] `pytest .../test_alerting_contract.py -v` 通过（若在 test-framework）

### 4) 筛选与监控页

- [ ] 历史带 `metric_key`+时间窗 → `filters` 与请求一致；**省略** `metric_key` → `filters.metric_key` 为 null
- [ ] `api.html`：有缓存时可先显缓存，手动 ↻ 与约 60s 自动刷新正常

### 5) 自动调度

- [ ] `AUTO_COLLECT Enabled` + 合理间隔，重启后日志显示调度；周期后可有账号 `last_sync_at` 更新

### 6) 异常

- [ ] 无 Cookie 同步 → 4xx，明确错误，不影响其他账号
- [ ] `start_at > end_at` → 400，`start_at 不能晚于 end_at`
- [ ] 非法告警参数 → 4xx，无脏数据

### 7) 发布通过标准

- [ ] 上述场景通过；告警契约测试通过；无核心 5xx
- [ ] 运行中配置与本文 §4、§5 一致

---

*更多产品说明见仓库根目录 [README.md](../README.md)。架构与数据模型见 [ARCHITECTURE.md](./ARCHITECTURE.md)。*
