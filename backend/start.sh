#!/usr/bin/env bash
# Token Monitor 后端一键启动：停旧进程 → 检查端口 → 创建虚拟环境 → 启动 uvicorn → 状态提示

set -euo pipefail

PORT=5188
BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$BACKEND_DIR/.venv"
REQ_FILE="$BACKEND_DIR/requirements.txt"
cd "$BACKEND_DIR"

echo "==> 工作目录: $BACKEND_DIR"

# 1) 停止占用本端口的旧进程
if command -v lsof >/dev/null 2>&1; then
  PIDS=$(lsof -ti ":$PORT" -sTCP:LISTEN 2>/dev/null || true)
  if [ -n "${PIDS:-}" ]; then
    echo "==> 停止占用端口 $PORT 的进程: $PIDS"
    kill $PIDS 2>/dev/null || true
    sleep 1
    PIDS=$(lsof -ti ":$PORT" -sTCP:LISTEN 2>/dev/null || true)
    if [ -n "${PIDS:-}" ]; then
      echo "==> 强制结束: $PIDS"
      kill -9 $PIDS 2>/dev/null || true
      sleep 1
    fi
  else
    echo "==> 未发现监听端口 $PORT 的旧进程"
  fi
else
  echo "==> 警告: 未找到 lsof，跳过按端口结束进程；将尝试匹配 uvicorn"
  pkill -f "uvicorn app:app.*--port ${PORT}" 2>/dev/null || true
  sleep 1
fi

# 2) 确认端口已释放
if command -v lsof >/dev/null 2>&1 && lsof -i ":$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "==> 错误: 端口 $PORT 仍被占用，请手动处理后重试。"
  exit 1
fi
if command -v ss >/dev/null 2>&1 && ss -tln 2>/dev/null | grep -q ":${PORT} "; then
  echo "==> 错误: 端口 $PORT 仍被占用 (ss 检测)，请手动处理后重试。"
  exit 1
fi
echo "==> 端口 $PORT 可用"

# 3) 创建虚拟环境（如不存在）
if [ -d "$VENV_DIR" ]; then
  echo "==> 虚拟环境已存在: $VENV_DIR"
else
  echo "==> 创建虚拟环境: $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

# 4) 安装依赖（如缺失）
PYTHON_BIN="$VENV_DIR/bin/python"
PIP_BIN="$VENV_DIR/bin/pip"
if ! "$PYTHON_BIN" -c 'import app' 2>/dev/null; then
  echo "==> 安装依赖: pip install -r requirements.txt"
  "$PIP_BIN" install -r "$REQ_FILE"
fi

# 5) 日志目录与启动
mkdir -p logs
LOG_FILE="$BACKEND_DIR/logs/backend.log"
export PYTHONUNBUFFERED=1
echo "==> 启动: nohup $PYTHON_BIN -m uvicorn app:app --host 0.0.0.0 --port $PORT"
nohup "$PYTHON_BIN" -m uvicorn app:app --host 0.0.0.0 --port "$PORT" >"$LOG_FILE" 2>&1 &
NEW_PID=$!
echo "==> 已后台启动，PID=$NEW_PID，日志: $LOG_FILE"

# 6) 等待端口监听：lifespan 内 init_db 等会推迟 bind，与 start.ps1 一致最多轮询 45s
_port_listening() {
  if command -v ss >/dev/null 2>&1 && ss -tln 2>/dev/null | grep -q ":${PORT} "; then
    return 0
  fi
  if command -v lsof >/dev/null 2>&1 && lsof -i ":$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

listened=0
i=0
while [ "$i" -lt 45 ]; do
  if _port_listening; then
    listened=1
    break
  fi
  if ! kill -0 "$NEW_PID" 2>/dev/null; then
    echo "==> 错误: 进程已退出，请查看日志尾部:"
    tail -n 40 "$LOG_FILE" 2>/dev/null || true
    exit 1
  fi
  i=$((i + 1))
  if [ "$((i % 5))" -eq 0 ]; then
    echo "==> 仍在等待端口 $PORT 监听… ($i/45，应用启动或数据库较慢)"
  fi
  sleep 1
done

if [ "$listened" -eq 1 ]; then
  echo "==> 状态: 端口 $PORT 正在监听"
else
  echo "==> 错误: 45s 内仍未检测到 $PORT 监听。日志尾部:"
  tail -n 40 "$LOG_FILE" 2>/dev/null || true
  exit 1
fi

echo "==> 完成。跟踪日志: tail -f $LOG_FILE"
