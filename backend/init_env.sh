#!/usr/bin/env bash
# Token Monitor — 生成 backend/.env 中的密钥并（可选）初始化 MySQL 库与用户
# 不覆盖已存在的 backend/.env

set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$BACKEND_DIR/.env"
EXAMPLE="$BACKEND_DIR/.env.example"

show_help() {
  cat <<'EOF'
用法: init_env.sh [选项]

  从 .env.example 复制生成 backend/.env，并写入随机生成的:
    APP_SECRET_KEY, JWT_SECRET_KEY, DB_PASSWORD (python secrets.token_urlsafe(32))

选项:
  -h, --help          显示本说明并退出
  --skip-mysql        不检测 MySQL、不尝试建库/用户

环境变量 (可选，用于自动建库与用户):
  INIT_MYSQL_ADMIN_USER       管理账号，默认 root
  INIT_MYSQL_ADMIN_PASSWORD   管理账号密码（若不设置则只写 .env，并提示手工建库）
  INIT_MYSQL_HOST             连接 MySQL 的主机，默认与 .env 中 DB_HOST 一致（见下）
  INIT_MYSQL_PORT             默认 3306

约束:
  • 若 backend/.env 已存在，脚本立即退出且不会修改任何文件。
  • 需要已安装 python3、mysql 客户端（未使用 --skip-mysql 且需自动建库时）。

示例:
  INIT_MYSQL_ADMIN_PASSWORD='your-root-pass' ./init_env.sh
  ./init_env.sh --skip-mysql
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  show_help
  exit 0
fi

SKIP_MYSQL=0
if [[ "${1:-}" == "--skip-mysql" ]]; then
  SKIP_MYSQL=1
fi

if [[ -f "$ENV_FILE" ]]; then
  echo "错误: 已存在 $ENV_FILE，为安全起见不会覆盖。请手动备份后删除再运行。" >&2
  exit 1
fi

if [[ ! -f "$EXAMPLE" ]]; then
  echo "错误: 缺少 $EXAMPLE" >&2
  exit 1
fi

python3 <<PY
import secrets
import shutil
from pathlib import Path

backend = Path(r"$BACKEND_DIR")
example = backend / ".env.example"
target = backend / ".env"
shutil.copyfile(example, target)

repl = {
    "JWT_SECRET_KEY": secrets.token_urlsafe(32),
    "APP_SECRET_KEY": secrets.token_urlsafe(32),
    "DB_PASSWORD": secrets.token_urlsafe(32),
}
lines = target.read_text(encoding="utf-8").splitlines()
out = []
for line in lines:
    s = line.strip()
    if (not s) or s.startswith("#") or "=" not in line:
        out.append(line)
        continue
    key, _, _ = line.partition("=")
    key = key.strip()
    if key in repl:
        out.append(f"{key}={repl[key]}")
    else:
        out.append(line)
target.write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"已生成: {target}")
PY

# 读取 .env 中的 DB_*（供连接检测）
load_env_kv() {
  python3 <<'PY'
from pathlib import Path
import os
p = Path(os.environ["ENV_FILE"])
d = {}
for line in p.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    d[k.strip()] = v.strip()
for key in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"):
    print(d.get(key, ""))
PY
}

export ENV_FILE
mapfile -t _dbvals < <(load_env_kv)
DB_HOST="${_dbvals[0]:-localhost}"
DB_PORT="${_dbvals[1]:-3306}"
DB_NAME="${_dbvals[2]:-token_monitor}"
DB_USER="${_dbvals[3]:-tm_user}"
DB_PASSWORD="${_dbvals[4]}"

INIT_MYSQL_ADMIN_USER="${INIT_MYSQL_ADMIN_USER:-root}"
INIT_MYSQL_HOST="${INIT_MYSQL_HOST:-$DB_HOST}"
INIT_MYSQL_PORT="${INIT_MYSQL_PORT:-3306}"

if [[ "$SKIP_MYSQL" -eq 1 ]]; then
  echo "已跳过 MySQL 检测 (--skip-mysql)。请手工建库授权后启动应用。"
  exit 0
fi

if ! command -v mysql >/dev/null 2>&1; then
  echo "警告: 未找到 mysql 客户端，跳过连接检测与自动建库。请安装 MySQL 客户端后手工执行 DEPLOYMENT.md 第 4 节。" >&2
  exit 0
fi

mysql_ping() {
  local user="$1" pass="$2" host="$3" port="$4"
  MYSQL_PWD="$pass" mysql -h"$host" -P"$port" -u"$user" -Nse "SELECT 1" >/dev/null 2>&1
}

if [[ -n "${INIT_MYSQL_ADMIN_PASSWORD:-}" ]]; then
  if ! mysql_ping "$INIT_MYSQL_ADMIN_USER" "$INIT_MYSQL_ADMIN_PASSWORD" "$INIT_MYSQL_HOST" "$INIT_MYSQL_PORT"; then
    echo "错误: 无法使用 INIT_MYSQL_ADMIN_USER 连接 MySQL（$INIT_MYSQL_HOST:$INIT_MYSQL_PORT）。" >&2
    exit 1
  fi
  export _INIT_SQL_DB_NAME="$DB_NAME" _INIT_SQL_DB_USER="$DB_USER" _INIT_SQL_DB_PASSWORD="$DB_PASSWORD"
  python3 <<'PY' | MYSQL_PWD="$INIT_MYSQL_ADMIN_PASSWORD" mysql -h"$INIT_MYSQL_HOST" -P"$INIT_MYSQL_PORT" -u"$INIT_MYSQL_ADMIN_USER"
import os

def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "''")

db = os.environ["_INIT_SQL_DB_NAME"]
user = os.environ["_INIT_SQL_DB_USER"]
pw = esc(os.environ["_INIT_SQL_DB_PASSWORD"])
user_esc = esc(user)
print(f"CREATE DATABASE IF NOT EXISTS `{db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
print(f"CREATE USER IF NOT EXISTS '{user_esc}'@'localhost' IDENTIFIED BY '{pw}';")
print(f"GRANT ALL PRIVILEGES ON `{db}`.* TO '{user_esc}'@'localhost';")
print("FLUSH PRIVILEGES;")
PY
  unset _INIT_SQL_DB_NAME _INIT_SQL_DB_USER _INIT_SQL_DB_PASSWORD
  echo "已尝试创建数据库 '$DB_NAME' 与用户 '$DB_USER'@'localhost'（需 MySQL 8+ 支持 CREATE USER IF NOT EXISTS）。"
else
  echo "提示: 未设置 INIT_MYSQL_ADMIN_PASSWORD，跳过自动建库。请用 root 手工执行 DEPLOYMENT.md 第 4 节，密码须与 .env 中 DB_PASSWORD 一致。"
fi

if mysql_ping "$DB_USER" "$DB_PASSWORD" "$DB_HOST" "$DB_PORT"; then
  echo "MySQL 检测通过: 用户 $DB_USER 可连接数据库 $DB_NAME。"
else
  echo "警告: 应用用户 $DB_USER 连接失败。请检查密码、主机权限或是否已 FLUSH PRIVILEGES。" >&2
  exit 1
fi
