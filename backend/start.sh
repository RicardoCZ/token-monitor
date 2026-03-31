#!/usr/bin/env bash
# Token Monitor 后端一键启动：停旧进程 → 检查端口 → 启动 uvicorn → 状态提示

set -euo pipefail

PORT=5188
BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

# 3) 日志目录与启动（与需求一致的 uvicorn 命令）
mkdir -p logs
LOG_FILE="$BACKEND_DIR/logs/backend.log"
echo "==> 启动: nohup python3 -m uvicorn app:app --host 0.0.0.0 --port $PORT"
nohup python3 -m uvicorn app:app --host 0.0.0.0 --port "$PORT" >"$LOG_FILE" 2>&1 &
NEW_PID=$!
echo "==> 已后台启动，PID=$NEW_PID，日志: $LOG_FILE"

sleep 1

# 4) 启动状态
if kill -0 "$NEW_PID" 2>/dev/null; then
  echo "==> 进程存活: PID $NEW_PID"
else
  echo "==> 警告: 进程已退出，请查看日志尾部:"
  tail -n 30 "$LOG_FILE" 2>/dev/null || true
  exit 1
fi

if command -v ss >/dev/null 2>&1 && ss -tlnp 2>/dev/null | grep -q ":${PORT}"; then
  echo "==> 状态: 端口 $PORT 正在监听 (ss)"
elif command -v lsof >/dev/null 2>&1 && lsof -i ":$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "==> 状态: 端口 $PORT 正在监听 (lsof)"
else
  echo "==> 警告: 暂未检测到 $PORT 监听，可能仍在加载；请稍后执行 ss -tlnp | grep $PORT 或看日志"
fi

echo "==> 完成。跟踪日志: tail -f $LOG_FILE"
