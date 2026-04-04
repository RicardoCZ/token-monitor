# Token Monitor 架构文档

本文档描述**数据模型、API、历史治理**。一键部署、迁移、`.env` 全表、日常命令、发布回归见 **[OPERATIONS.md](./OPERATIONS.md)**。

## 1. 数据模型

### 1.1 核心实体

- `users`：系统用户（管理员/普通用户）
- `services`：服务注册表（服务元数据、`capabilities`、`metric_defs`）
- `accounts`：用户绑定的服务账号（加密 Cookie、`group_id`、采集状态）
- `usage_snapshots`：用量历史事实表（单轨）
- `alerts`：告警规则（`account_id + metric_key` 维度）
- `alert_events`：告警事件流（触发/恢复）
- `invite_codes`、`api_keys`：认证与访问控制辅助表

### 1.2 关键关系

- `users 1 - n accounts`
- `services 1 - n accounts`
- `accounts 1 - n usage_snapshots`
- `accounts 1 - n alerts`
- `alerts 1 - n alert_events`

### 1.3 历史数据策略

- 历史事实源统一为 `usage_snapshots`（不再读写 `usage_history`）
- 默认保留窗口：最近 90 天
- 历史清理默认处理两类高增长表：
  - `usage_snapshots`（按 `collected_at`）
  - `alert_events`（按 `created_at`）
- 支持按账号维度选择性清理，便于分批治理和问题回滚评估

## 2. API

### 2.1 认证与用户

- `POST /auth/login`：登录
- `POST /auth/register`：注册（邀请码）
- `GET /auth/me`：当前用户信息
- `GET /auth/setup-status`、`POST /auth/setup-first`：首次管理员初始化

### 2.2 服务与账号

- `GET /api/services`：服务注册表（含 `metric_defs`）
- `GET /api/accounts`：账号列表
- `POST /api/accounts`：创建/更新账号 Cookie
- `PUT /api/accounts/{id}`：更新账号
- `DELETE /api/accounts/{id}`：删除账号
- `POST /api/accounts/{id}/sync`：手动同步用量

### 2.3 历史与告警

- `GET /api/accounts/{id}/history`
  - 查询参数：`limit`、`offset`、`start_at`、`end_at`；`metric_key` **可选**（省略则不按指标过滤）
  - 返回结构：`source + pagination + filters + items`
- `GET /api/accounts/{id}/alerts`：规则列表
- `PUT /api/accounts/{id}/alerts/{metric_key}`：规则 upsert
- `GET /api/accounts/{id}/alerts/events`：事件流

### 2.4 服务专用接口

- `GET /api/minimax/`
- `GET /api/xfyun/`
- `GET /api/cdp/services`、`POST /api/cdp/connect` 等 CDP 辅助接口

## 3. 部署与配置（摘要）

- **运行环境**：Python 3.10+、MySQL 8.x、FastAPI + SQLAlchemy Async + aiomysql。
- **迁移 / 启动 / 健康检查 / 完整 `PORT` 与各 env 说明**：见 [OPERATIONS.md](./OPERATIONS.md)。
- 服务启动时会 `init_db`、seed 服务注册表、按 `AUTO_COLLECT_*` 等配置启停自动采集。

## 4. 运维与数据治理（P2-5）

### 4.1 保留策略

- 建议值：90 天（可按业务量调整）
- 清理动作建议低峰执行，先 `dry-run`，再正式删除

### 4.2 清理脚本

脚本路径：`backend/utils/cleanup_history_data.py`

常用命令：

```bash
cd /mnt/d/wsl/share/new/backend

# 预览全量（默认 90 天）
python3 -m utils.cleanup_history_data --dry-run

# 仅清理指定账号（可多次传 --account-id）
python3 -m utils.cleanup_history_data --account-id 12 --account-id 18 --dry-run

# 带回滚检查执行
python3 -m utils.cleanup_history_data --rollback-check
```

### 4.3 回滚检查说明

- `--rollback-check` 会按账号输出：
  - 清理前总量
  - 预计删除量
  - 清理后保留量
  - 保留数据中的最新时间
- 当某账号清理后无保留数据时会输出告警提示，便于先行复核
