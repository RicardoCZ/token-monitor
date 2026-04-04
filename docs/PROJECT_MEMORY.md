# Token Monitor Project Memory

## 项目定位
- 项目：`Token Monitor`
- 路径：`/mnt/d/wsl/share/new`
- 当前主线：服务注册表重构 + `usage_snapshots` 单轨 + 自动采集 + 告警链路

## 当前状态（2026-04-04）
- 后端主线：
  - 服务注册表、`usage_snapshots` 单轨、自动采集、告警链路已落地
  - 指标键统一主线已收敛到 `used / total / percent`（历史兼容清理已推进）
  - `GET /api/accounts/{id}/history` 的 `metric_key` **可选**：省略则不在 SQL 中按指标过滤（前端 `history.html` 已不传该参数）
- 前端主线：
  - 账号管理页（`accounts.html`）已承担账号与告警核心交互
  - 管理后台（`admin.html`）聚焦邀请码/API Key；账号相关能力已迁移
  - 监控页（`api.html`）已支持缓存回显 + 后台刷新，减少返回页面空白等待
  - 历史趋势**仅**独立页（`history.html`）：ECharts 双 Y 轴（percent / used）、时间轴全窗口、断点不连接、状态栏实际范围与覆盖率；`api.html` 不内嵌图表，仅导航入口
- 待办请看：`/mnt/d/wsl/share/new/TODO.md`

## 文档索引（避免重复查阅）

| 文档 | 用途 |
|------|------|
| [OPERATIONS.md](./OPERATIONS.md) | 部署、迁移、`.env` 全表、Runbook、**发布回归** |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 数据模型、API 索引、历史清理脚本 |
| [DEVELOPMENT.md](./DEVELOPMENT.md) | UI/协作规范、安全依赖基线、Alice 验证清单 |
| [DECISIONS.md](./DECISIONS.md) | ADR |
| [KNOWN_ISSUES.md](./KNOWN_ISSUES.md) | 已知问题 |
| 根目录 `DEPLOYMENT.md` | 指向 `OPERATIONS.md` 的短链 |

## 关键技术决策
- 历史趋势页面策略：**独立 `history.html` 单一职责**；实时监控页不合并图表以避免脚本臃肿
- 历史数据事实源：`usage_snapshots`
- 历史查询契约：
  - `GET /api/accounts/{id}/history`
  - 查询参数：`limit`、`offset`、`start_at`、`end_at`；`metric_key` **可选**（缺省不过滤）
  - 返回固定结构：`source + pagination + filters + items`
- 自动采集与手动同步复用同一采集主逻辑（`collect_account_usage`）
- 告警评估基于最新快照，规则维度是 `account_id + metric_key`

## 当前前端交互约定（重要）
- 列表区域统一结构：`标题 -> 内容 -> 分页`
- 切换筛选/分页/账号优先局部刷新，不先清空容器，避免闪烁
- 自定义下拉必须保留隐藏原字段并触发 `change`，不破坏原逻辑
- 保存类操作默认提供明确反馈（成功 toast / 失败错误提示）

## 关键配置开关（backend/.env）
- 自动采集：
  - `AUTO_COLLECT_ENABLED`
  - `AUTO_COLLECT_INTERVAL_SECONDS`
  - `AUTO_COLLECT_MAX_CONCURRENCY`
  - `AUTO_COLLECT_RETRY_ATTEMPTS`
  - `AUTO_COLLECT_RETRY_DELAY_SECONDS`
- 告警评估：
  - `ALERT_EVAL_ENABLED`
  - `ALERT_DEFAULT_THRESHOLD`
  - `ALERT_DEFAULT_COOLDOWN_SECONDS`

## 明天快速上手流程
1. 先读本文件：`docs/PROJECT_MEMORY.md`
2. 再读任务清单：`TODO.md`
3. 查看当前分支状态：`git status --short --branch`
4. 启动前确认配置：`backend/.env`（采集与告警开关）
5. 发布前可按 [OPERATIONS.md §10](./OPERATIONS.md#10-发布回归-checklist) 做快速回归；日常含 `api.html`、`history.html`、`accounts.html`、`admin.html`
6. 按 `TODO.md` 中最高优先级任务继续

## 给 AI 的开场提示（可直接复制）
请先阅读 `docs/PROJECT_MEMORY.md` 和 `TODO.md`，按 TODO 中最高优先级继续开发，不要重复已完成任务；如果需要改动，先给最小可交付实现并验证。历史趋势已落在 `history.html`；验证 HTTP 时以 `backend/.env` 的 `PORT` 为准。
