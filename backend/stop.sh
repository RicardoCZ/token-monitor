#!/usr/bin/env bash
# Token Monitor 后端一键停止：释放监听进程（与 stop.ps1 行为一致）

set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$BACKEND_DIR/.env"
cd "$BACKEND_DIR"

PORT=5188
if [[ -f "$ENV_FILE" ]]; then
  _line="$(grep -E '^[[:space:]]*PORT=' "$ENV_FILE" | tail -n1 || true)"
  if [[ -n "${_line:-}" ]]; then
    PORT="${_line#*=}"
    PORT="${PORT//$'\r'/}"
    PORT="${PORT//\"/}"
    PORT="${PORT//\'/}"
  fi
fi

echo "==> 正在关闭 Token Monitor 后端服务（端口 $PORT）..."

PIDS=""
if command -v lsof >/dev/null 2>&1; then
  PIDS=$(lsof -ti ":$PORT" -sTCP:LISTEN 2>/dev/null || true)
fi

if [ -z "${PIDS:-}" ]; then
  echo "==> 未发现监听端口 $PORT 的进程；尝试 fuser 或 pkill"
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${PORT}/tcp" 2>/dev/null || true
  else
    pkill -f "uvicorn app:app.*--port ${PORT}" 2>/dev/null || true
  fi
  sleep 1
  echo "==> 完成（若仍有进程请用 ss -tlnp 或 lsof -i :$PORT 检查）"
  exit 0
fi

echo "==> 停止占用端口 $PORT 的进程: $PIDS"
kill $PIDS 2>/dev/null || true
sleep 1

PIDS=$(lsof -ti ":$PORT" -sTCP:LISTEN 2>/dev/null || true)
if [ -n "${PIDS:-}" ]; then
  echo "==> 强制结束: $PIDS"
  kill -9 $PIDS 2>/dev/null || true
  sleep 1
fi

if command -v lsof >/dev/null 2>&1 && lsof -i ":$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "==> 警告: 端口 $PORT 仍被占用，请手动处理。" >&2
  exit 1
fi

echo "==> Token Monitor 后端服务已关闭"
