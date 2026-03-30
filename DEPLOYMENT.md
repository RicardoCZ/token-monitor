# Token Monitor 部署指南

面向**全新环境**的后端 + Web 静态资源部署（项目根目录：`share/new/`）。配置项名称与占位说明以仓库内 **`backend/.env.example`** 为准；本文不重复罗列每个环境变量的注释，仅说明必须执行的步骤与命令。

---

## 1. 环境要求

| 项目 | 版本 / 说明 |
|------|-------------|
| Python | **3.10+**（推荐 3.11、3.12） |
| MySQL | **5.7+**，或 8.0+（字符集建议 `utf8mb4`） |
| 操作系统 | Linux / macOS / WSL；Windows 可直接装 Python + MySQL 或使用 WSL |
| 网络 | 服务器需能访问 MiniMax / 讯飞等上游站点（按业务需要） |

**依赖安装**（在 `backend/` 目录，建议使用虚拟环境）：

```bash
cd backend
python3 -m venv .venv
# Linux / macOS:
source .venv/bin/activate
# Windows CMD:
# .venv\Scripts\activate.bat

pip install -U pip
pip install -r requirements.txt
```

确认 Python 版本：

```bash
python3 --version   # 应显示 3.10 或更高
```

---

## 2. 密钥生成与配置

**原则**：开发、测试、生产等**每个环境各自生成一套密钥**，禁止多环境共用；**禁止**将真实 `.env` 提交到 Git（仓库已 `.gitignore` `backend/.env`）。

### 2.1 生成 `JWT_SECRET_KEY` 与 `APP_SECRET_KEY`

二者均须为**强随机串**（至少满足应用校验长度要求：`APP_SECRET_KEY`、`JWT_SECRET_KEY` 各 ≥ 16 字符，建议更长）。使用项目约定命令：

```bash
# JWT 签名密钥（每条各执行一次，勿复用输出）
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# 应用加密密钥（Cookie 等）
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

将**两次**命令输出的字符串分别填入 `backend/.env` 中的 `JWT_SECRET_KEY` 与 `APP_SECRET_KEY`。

### 2.2 生成 `DB_PASSWORD`

MySQL 用户 `tm_user` 的登录密码须与 `.env` 中 **`DB_PASSWORD` 完全一致**。可与上式相同方式生成随机口令（仅作口令，不是 JWT）：

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

在 **MySQL 里创建用户 / 授权时使用该口令**（见第 3 节），并把同一字符串写入 `DB_PASSWORD=`。

### 2.3 写入 `.env`

```bash
cp backend/.env.example backend/.env
# 编辑 backend/.env，填入上述密钥与数据库口令，并核对 DB_HOST、DB_NAME、DB_USER 等
```

未在 `.env.example` 中展开的变量含义，请仅通过 **`backend/core/config.py`** 中的 `Settings` 定义核对（勿把生产值写进文档或截图进仓库）。

---

## 3. 数据库创建与用户授权

使用具备管理权限的 MySQL 账号（如 `root`）登录后执行（可按需修改库名、用户名、`主机` 部分）：

```sql
-- 创建库（与应用默认 DB_NAME 一致，可按 .env 修改）
CREATE DATABASE IF NOT EXISTS token_monitor
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- 创建业务用户（与 DB_USER 一致；密码替换为第 2.2 节生成的口令）
CREATE USER IF NOT EXISTS 'tm_user'@'localhost' IDENTIFIED BY '这里填 DB_PASSWORD 同款口令';

-- 仅本机连接可把 host 改为 'localhost'；远程应用可改为 '%' 或指定应用服务器 IP
GRANT ALL PRIVILEGES ON token_monitor.* TO 'tm_user'@'localhost';

FLUSH PRIVILEGES;
```

说明：

- `tm_user`、库名 `token_monitor` 须与 **`backend/.env`** 中 `DB_USER`、`DB_NAME` 一致。
- 若应用与 MySQL 不同机，将 `'tm_user'@'localhost'` 改为 `'tm_user'@'%'` 或具体客户端地址，并保证 MySQL 监听与防火墙放行 **第 2.2 节** 同一口令。
- **不要**把真实口令写进仓库；仅保存在 `.env` 与 MySQL 中。

应用首次启动时会通过 ORM **自动建表**（`init_db`），无需手工导入表结构 SQL。

---

## 4. 启动与验证

### 4.1 启动 API

在已激活虚拟环境、`backend/.env` 已就绪的前提下：

```bash
cd backend
source .venv/bin/activate   # Windows 使用对应 activate 脚本

uvicorn app:app --host 0.0.0.0 --port 5188
```

或使用仓库内脚本（若存在）：

```bash
./start.sh
```

默认：`HOST`/`PORT` 可由 `.env` 中配置；静态前端由 FastAPI 挂载 **`frontend/`**（与 `backend` 同级的目录）。

### 4.2 验证步骤

1. **健康检查**：浏览器或 curl 访问 `http://<HOST>:<PORT>/`（或静态页如 `login.html`），应返回 Web 页面而非连接拒绝。
2. **API**：例如 `GET http://127.0.0.1:5188/api/health` 或 `GET http://127.0.0.1:5188/api/status`，应返回 JSON 而非连接错误。
3. **数据库**：启动日志中不应出现 MySQL 认证失败；首次启动应完成表创建。
4. **首任管理员**（数据库中尚无用户时）：调用 `POST /auth/create-admin`。初始口令：**优先**设置环境变量 `ADMIN_PASSWORD`（≥12 字符）；否则首次调用会在 `data/admin_secret.txt` 写入随机口令。**响应正文不含密码**，请从环境变量或该文件读取后登录并尽快改密（**生产务必限制该接口暴露面**）。

若上述任一步失败，结合第 5 节排查。

---

## 5. 常见错误与处理

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 启动即报 Pydantic `ValidationError`，提示 `jwt_secret_key` / `app_secret_key` / `db_password` | `.env` 未配置或长度不足 | 完成第 2 节；`JWT_SECRET_KEY` 与 `APP_SECRET_KEY` 各 ≥ 16 字符 |
| `Access denied for user 'tm_user'@...` | 密码与 `DB_PASSWORD` 不一致，或主机未授权 | 核对 MySQL `IDENTIFIED BY` 与 `.env`；检查 `CREATE USER` 的 host |
| `Can't connect to MySQL server` | MySQL 未启动 / 防火墙 / `DB_HOST` 错误 | 确认服务监听、`DB_HOST`、`DB_PORT` |
| 端口被占用 | 5188 已有进程 | 修改 `.env` 中 `PORT` 或结束占用进程后再启动 |
| 静态页 404 | `frontend/` 不在 `backend` 的上一级 | 保持仓库目录结构：`new/backend`、`new/frontend` 并存 |
| 依赖安装失败 | Python 版本过低或 pip 源问题 | 升级到 Python 3.10+；换官方或镜像源重试 |

---

## 6. 部署后安全建议（摘要）

- 生产环境关闭 `DEBUG`，使用 HTTPS 反向代理（Nginx 等），并收紧 CORS。
- 定期更换密钥时：**JWT_SECRET_KEY** 变更会导致已签发 token 全部失效，需通知用户重新登录。
- 勿将 `backend/.env`、数据库口令贴入 issue 或公开聊天日志。

---

*更细致的接口与前端说明见仓库根目录 **README.md**。*
