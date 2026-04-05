#!/usr/bin/env bash
# Token Monitor 后端一键停止：释放 5188 监听进程（与 stop.ps1 行为一致）

set -euo pipefail

PORT=5188
BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BACKEND_DIR"

echo "==> 正在关闭 Token Monitor 后端服务（端口 $PORT）..."

PIDS=""
if command -v lsof >/dev/null 2>&1; then
  PIDS=$(lsof -ti ":$PORT" -sTCP:LISTEN 2>/dev/null || true)
fi

if [ -z "${PIDS:-}" ]; then
  echo "==> 未发现监听端口 $PORT 的进程；尝试匹配 uvicorn"
  pkill -f "uvicorn app:app.*--port ${PORT}" 2>/dev/null || true
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
