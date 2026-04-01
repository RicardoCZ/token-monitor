# Token Monitor — 生成 backend/.env 密钥并（可选）初始化 MySQL（Windows PowerShell）
# 不覆盖已存在的 backend/.env

param(
    [switch]$Help,
    [switch]$SkipMySql
)

$ErrorActionPreference = "Stop"
$BackendDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $BackendDir ".env"
$Example = Join-Path $BackendDir ".env.example"

function Show-Help {
    @'
用法: .\init_env.ps1 [-Help] [-SkipMySql]

  从 .env.example 复制生成 backend\.env，并写入随机生成的:
    APP_SECRET_KEY, JWT_SECRET_KEY, DB_PASSWORD
    (均使用: python -c "import secrets; print(secrets.token_urlsafe(32))")

参数:
  -Help          显示本说明
  -SkipMySql     不检测 MySQL、不尝试建库

环境变量 (可选，自动建库):
  $env:INIT_MYSQL_ADMIN_USER       默认 root
  $env:INIT_MYSQL_ADMIN_PASSWORD   若不设置则仅提示手工建库
  $env:INIT_MYSQL_HOST             默认与 .env 中 DB_HOST 一致
  $env:INIT_MYSQL_PORT             默认 3306

约束:
  • 若 backend\.env 已存在，脚本立即退出。
  • 需要 python、mysql 在 PATH 中（建库/G检测时）。

示例:
  $env:INIT_MYSQL_ADMIN_PASSWORD='your-root-pass'; .\init_env.ps1
  .\init_env.ps1 -SkipMySql
'@ | Write-Host
}

if ($Help) {
    Show-Help
    exit 0
}

if (Test-Path -LiteralPath $EnvFile) {
    Write-Error "已存在 $EnvFile，为安全起见不会覆盖。请先备份并删除后再运行。"
    exit 1
}

if (-not (Test-Path -LiteralPath $Example)) {
    Write-Error "缺少 $Example"
    exit 1
}

$bdirPy = $BackendDir.Replace('\', '/')
$fillPy = @'
import secrets
import shutil
from pathlib import Path

backend = Path(r"__BDIR__")
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
print("OK", target)
'@.Replace('__BDIR__', $bdirPy)

$fillPy | python -
if ($LASTEXITCODE -ne 0) {
    Write-Error "Python 生成 .env 失败"
    exit 1
}

function Read-DotEnv {
    param([string]$Path)
    $d = @{}
    Get-Content -LiteralPath $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $i = $line.IndexOf("=")
        if ($i -lt 0) { return }
        $k = $line.Substring(0, $i).Trim()
        $v = $line.Substring($i + 1).Trim()
        $d[$k] = $v
    }
    return $d
}

if ($SkipMySql) {
    Write-Host "已跳过 MySQL (-SkipMySql)。请手工建库后启动。"
    exit 0
}

if (-not (Get-Command mysql -ErrorAction SilentlyContinue)) {
    Write-Warning "未找到 mysql.exe，跳过连接检测。请安装客户端，参见 docs/MIGRATION_GUIDE.md（2. 迁移脚本说明）与 docs/CONFIG_MANUAL.md（2. 配置项总览）手工处理。"
    exit 0
}

$cfg = Read-DotEnv -Path $EnvFile
$dbHost = if ($cfg["DB_HOST"]) { $cfg["DB_HOST"] } else { "localhost" }
$dbPort = if ($cfg["DB_PORT"]) { $cfg["DB_PORT"] } else { "3306" }
$dbName = if ($cfg["DB_NAME"]) { $cfg["DB_NAME"] } else { "token_monitor" }
$dbUser = if ($cfg["DB_USER"]) { $cfg["DB_USER"] } else { "tm_user" }
$dbPass = $cfg["DB_PASSWORD"]

$adminUser = if ($env:INIT_MYSQL_ADMIN_USER) { $env:INIT_MYSQL_ADMIN_USER } else { "root" }
$adminHost = if ($env:INIT_MYSQL_HOST) { $env:INIT_MYSQL_HOST } else { $dbHost }
$adminPort = if ($env:INIT_MYSQL_PORT) { $env:INIT_MYSQL_PORT } else { "3306" }

function Test-MysqlConn {
    param(
        [string]$User,
        [string]$Password,
        [string]$Host,
        [string]$Port
    )
    $env:MYSQL_PWD = $Password
    try {
        & mysql -h$Host -P$Port -u$User -Nse "SELECT 1" 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } finally {
        Remove-Item Env:MYSQL_PWD -ErrorAction SilentlyContinue
    }
}

if ($env:INIT_MYSQL_ADMIN_PASSWORD) {
    if (-not (Test-MysqlConn -User $adminUser -Password $env:INIT_MYSQL_ADMIN_PASSWORD -Host $adminHost -Port $adminPort)) {
        Write-Error "无法用管理账号连接 MySQL ${adminHost}:${adminPort}。"
        exit 1
    }
    $sqlPy = @'
import os
def esc(s):
    return s.replace("\\", "\\\\").replace("'", "''")
db = os.environ["_D"]
user = os.environ["_U"]
pw = esc(os.environ["_P"])
ue = esc(user)
print(f"CREATE DATABASE IF NOT EXISTS `{db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
print(f"CREATE USER IF NOT EXISTS '{ue}'@'localhost' IDENTIFIED BY '{pw}';")
print(f"GRANT ALL PRIVILEGES ON `{db}`.* TO '{ue}'@'localhost';")
print("FLUSH PRIVILEGES;")
'@
    $env:_D = $dbName
    $env:_U = $dbUser
    $env:_P = $dbPass
    try {
        $env:MYSQL_PWD = $env:INIT_MYSQL_ADMIN_PASSWORD
        $sqlPy | python - | & mysql -h$adminHost -P$adminPort -u$adminUser
        if ($LASTEXITCODE -ne 0) {
            Write-Error "建库 SQL 执行失败"
            exit 1
        }
    } finally {
        Remove-Item Env:MYSQL_PWD -ErrorAction SilentlyContinue
        Remove-Item Env:_D -ErrorAction SilentlyContinue
        Remove-Item Env:_U -ErrorAction SilentlyContinue
        Remove-Item Env:_P -ErrorAction SilentlyContinue
    }
    Write-Host "已尝试创建数据库 '$dbName' 与用户 '$dbUser'@'localhost'（需 MySQL 8+）。"
} else {
    Write-Host "未设置 INIT_MYSQL_ADMIN_PASSWORD，跳过自动建库。请参见 docs/MIGRATION_GUIDE.md（2. 迁移脚本说明）与 docs/CONFIG_MANUAL.md（2. 配置项总览）手工执行。"
}

if (Test-MysqlConn -User $dbUser -Password $dbPass -Host $dbHost -Port $dbPort) {
    Write-Host "MySQL 检测通过: 用户 $dbUser 可连接。"
} else {
    Write-Error "应用用户 $dbUser 连接失败，请检查授权与 DB_PASSWORD。"
    exit 1
}
