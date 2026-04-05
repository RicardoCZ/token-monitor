# Token Monitor 部署指南

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
启动时 `init_db()` 会执行 SQLAlchemy `create_all`：**仅创建库中尚不存在的表**，不会给已有表自动加列/删列。**全新空库**首次启动前需已建好数据库并配置好 `backend/.env`（可用 `init_env.sh` / `init_env.ps1`）。若某张表早已存在但缺新字段，需手工 `ALTER` 或删表后再启（开发环境常见）。

此外，每次启动会在事务中执行一条**幂等**结构补丁：将 `services.icon` 加宽为 `VARCHAR(128)`（兼容历史 `VARCHAR(10)` 存不下 `/icons/*.ico` 路径的情况）。若数据库用户无 `ALTER` 权限，需 DBA 手工执行：  
`ALTER TABLE services MODIFY COLUMN icon VARCHAR(128) NULL;`

---

## 配置与安全

- 复制 `backend/.env.example` 为 `backend/.env` 并填写密钥与数据库连接。
- **勿提交** `backend/.env`；生产环境关闭 `DEBUG`，HTTPS。
- 常见问题：`.env 已存在` 时初始化脚本不会覆盖；端口占用可改 `PORT` 或结束占用进程。

---

## 更多

- 产品说明、**Web 前端脚本约定**、**Android 打包**（含 `pack.sh`、设计预览里 `prepare_launcher_icons.py`、`public/welcome-logo`）、**adb 安装**见 **[README.md](./README.md)**。

### 手机端 APK 与图标（摘要）

- 更新壳内 H5：**在 `mobile-app/`** 执行 `npm run build` 与 `npx cap sync android` 后再打 APK；或直接 **`bash pack.sh`**。
- 更换**应用图标**或欢迎页顶图：见 README「启动器图标与 welcome-logo」；依赖 Pillow，在 `design-preview` 运行 `python3 prepare_launcher_icons.py`。
