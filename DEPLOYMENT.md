# Token Monitor 部署指南

> **说明**：详细运维手册（完整 `.env` 表、Runbook、发布回归清单等）在本地维护的 **`docs/OPERATIONS.md`** 中；该 **`docs/` 目录不参与远端仓库**，仅供本地或内部分发。

面向**全新环境**的最低限度流程如下。配置项仍以 `backend/.env.example` 为准。

---

## 快速启动（一键）

**前提**：Python 3.10+、**MySQL 8.0+** 已安装且已启动。

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

浏览器访问 `http://localhost:<PORT>`（`<PORT>` 见 `backend/.env`，默认 5188）。

---

## 数据库迁移（按需）

在 `backend/` 目录建议按顺序执行（可重复执行）：

```bash
cd backend
python3 -m utils.migrate_service_registry
python3 -m utils.migrate_alerting_p2_3
python3 -m utils.migrate_api_keys
```

---

## 配置与安全

- 复制 `backend/.env.example` 为 `backend/.env` 并填写密钥与数据库连接。
- **勿提交** `backend/.env`；生产环境关闭 `DEBUG`，HTTPS。
- 常见问题：`.env 已存在` 时初始化脚本不会覆盖；端口占用可改 `PORT` 或结束占用进程。

---

## 更多

- 产品说明与 API 摘要见根目录 **[README.md](./README.md)**。
- 若本地存在 **`docs/`** 目录，可打开 **`docs/OPERATIONS.md`** 获取完整运维手册。
