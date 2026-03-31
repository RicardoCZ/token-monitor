# Token Monitor 部署指南

面向**全新环境**的部署流程。配置项说明见 `backend/.env.example`。

---

## 快速开始（5 步完成）

| 步骤 | 操作 |
|------|------|
| 0 | **MySQL 管理员账户**：先设置好 root（或管理员）密码 |
| 1 | 安装 Python 3.10+ 和 MySQL 5.7+（推荐 8.0+），MySQL 已启动 |
| 2 | `cd backend && pip install -r requirements.txt` |
| 3 | 运行初始化脚本（见下方），生成密钥和 `.env` |
| 4 | 启动：`uvicorn app:app --host 0.0.0.0 --port 5188` |
| 5 | 打开前端 `login.html`（或移动端 App），在**首次引导**中创建管理员账号 |

---

## 数据库迁移（API Key）

在升级到包含 API Key 鉴权的版本后，请执行一次迁移脚本以创建 `api_keys` 表和相关索引：

```bash
cd backend
python -m utils.migrate_api_keys
```

> 如果你的环境使用 `python3`，请将命令改为 `python3 -m utils.migrate_api_keys`。

---

## 初始化脚本

> ⚠️ **前提**：先确保 MySQL 管理员账户（如 root）已有密码，脚本需要用它来创建数据库和用户。

**脚本不会覆盖已存在的 `.env`。**

### 命令对比

| 操作 | Unix (WSL/macOS) | Windows (PowerShell) |
|------|------------------|---------------------|
| 查看帮助 | `./init_env.sh --help` | `.\init_env.ps1 -Help` |
| 生成密钥（不连 MySQL） | `./init_env.sh --skip-mysql` | `.\init_env.ps1 -SkipMySql` |
| 生成密钥 + 自动建库 | `export INIT_MYSQL_ADMIN_USER='root' INIT_MYSQL_ADMIN_PASSWORD='MySQL管理员密码' && ./init_env.sh` | `$env:INIT_MYSQL_ADMIN_USER = "root"; $env:INIT_MYSQL_ADMIN_PASSWORD = "MySQL管理员密码"; .\init_env.ps1` |

> 用户名默认 `root`；密码必填（MySQL 管理员密码）才能自动建库。可选参数：`INIT_MYSQL_HOST`、`INIT_MYSQL_PORT`、`INIT_MYSQL_ADMIN_USER`。

### 成功后的操作

1. **启动后端**：`uvicorn app:app --host 0.0.0.0 --port 5188`

2. **创建管理员**：浏览器访问登录页（或 `/first-setup.html`）；空库时会显示引导，调用 `POST /auth/setup-first` 由前端完成。也可用 API 客户端在无用户时直接请求该接口。

---

## 手工建库（不用脚本时）

用 MySQL 管理账号执行：

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
| `.env 已存在` | 脚本保护机制；删掉 `backend/.env` 重来，或手动编辑 |
| `ValidationError` | 检查 `.env` 必填项是否完整（见 `.env.example`）|
| `Access denied` | 确认 MySQL 用户密码与 `.env` 中 `DB_PASSWORD` 一致 |
| `Can't connect` | 检查 MySQL 服务、`DB_HOST`、`DB_PORT` |
| 端口占用 | 改 `.env` 中 `PORT`，或结束占用进程 |

---

## 安全提醒

- **不要提交** `backend/.env` 到 Git
- 生产环境关闭 `DEBUG`，使用 HTTPS
- 轮换 `JWT_SECRET_KEY` 会使所有已登录用户失效

---

## API Key 使用

### 1) 在管理后台创建 API Key

1. 管理员登录 `admin.html`
2. 在「API Key 管理」区域填写名称、Scope、可选过期时间
3. 点击创建并立即复制明文 Key（只显示一次）

权限说明：普通用户只能管理自己的 Key，管理员可管理全部用户的 Key。

### 2) 程序调用示例

```bash
# 推荐：X-API-Key 头
curl "http://localhost:5188/api/current-cookies" \
  -H "X-API-Key: tmk_xxx"

# 或 Authorization: ApiKey 头
curl "http://localhost:5188/api/current-cookies" \
  -H "Authorization: ApiKey tmk_xxx"
```

常用 Scope：

- `cookie:read`
- `cookie:write`

---

*更多说明见 [README.md](./README.md)。*
