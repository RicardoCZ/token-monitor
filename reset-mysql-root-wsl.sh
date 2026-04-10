#!/usr/bin/env bash
# MySQL 8 (WSL/Ubuntu): reset local root password.
# Run:  sudo bash reset-mysql-root-wsl.sh 'YourNewStrongPassword'
set -euo pipefail

RESET_CNF="/etc/mysql/mysql.conf.d/z-temp-skip-grant-tables.cnf"

rm_reset_cnf() { rm -f "$RESET_CNF"; }
trap rm_reset_cnf EXIT

if [[ "${EUID:-}" -ne 0 ]]; then
  echo "请用 root 执行（会提示你输入 WSL 用户密码）："
  echo "  sudo bash $0 '你的新密码'"
  exit 1
fi

NEW_PASS="${1:-}"
if [[ -z "$NEW_PASS" ]]; then
  echo "用法: sudo bash $0 '你的新密码'"
  exit 1
fi

# MySQL: escape single quotes in password for quoted string literal
sql_escape() { printf '%s' "$1" | sed "s/'/''/g"; }
ESC_PASS="$(sql_escape "$NEW_PASS")"

cat >"$RESET_CNF" <<'EOF'
[mysqld]
skip-grant-tables
skip-networking
EOF

systemctl stop mysql
systemctl start mysql

for _ in $(seq 1 30); do
  mysqladmin ping -u root --silent 2>/dev/null && break
  sleep 1
done

mysql -u root <<SQL
FLUSH PRIVILEGES;
ALTER USER 'root'@'localhost' IDENTIFIED BY '${ESC_PASS}';
FLUSH PRIVILEGES;
SQL

rm_reset_cnf
trap - EXIT

systemctl restart mysql

echo
echo "已重置。验证: mysql -u root -p"
