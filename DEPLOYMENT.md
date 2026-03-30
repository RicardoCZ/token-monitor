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
| 5 | 调用 `POST /auth/create-admin` 创建管理员 |

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

1. **加载管理员口令**（必须与启动后端同一个 shell）：
   - Unix: `source backend/.admin_password.env`
   - Windows: `. .\backend\.admin_password.env.ps1`

2. **启动后端**：`uvicorn app:app --host 0.0.0.0 --port 5188`

3. **创建管理员**：`POST /auth/create-admin`（响应不含明文密码）

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

- **不要提交** `backend/.env` 和 `backend/.admin_password.env*` 到 Git
- 生产环境关闭 `DEBUG`，使用 HTTPS
- 轮换 `JWT_SECRET_KEY` 会使所有已登录用户失效

---

*更多说明见 [README.md](./README.md)。*
