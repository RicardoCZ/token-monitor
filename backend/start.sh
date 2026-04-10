#!/usr/bin/env bash
# Token Monitor 后端一键启动：停旧进程 → 检查端口 → 创建虚拟环境 → 启动 uvicorn → 状态提示

set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$BACKEND_DIR/.venv"
REQ_FILE="$BACKEND_DIR/requirements.txt"
ENV_FILE="$BACKEND_DIR/.env"
cd "$BACKEND_DIR"

# 端口：与 core/config 一致，优先 .env 中 PORT，默认 5188
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

# 虚拟环境 Python：须 3.9+（aiomysql>=0.3 等）；优先较新版本
pick_venv_python() {
  local c maj min
  for c in python3.12 python3.11 python3.10 python3.9; do
    if command -v "$c" >/dev/null 2>&1; then
      read -r maj min < <("$c" -c 'import sys; print(sys.version_info[0], sys.version_info[1])' 2>/dev/null) || continue
      if [[ "${maj:-0}" -eq 3 ]] && [[ "${min:-0}" -ge 9 ]]; then
        echo "$c"
        return 0
      fi
    fi
  done
  if command -v python3 >/dev/null 2>&1; then
    echo "python3"
    return 0
  fi
  return 1
}

VENV_PY="$(pick_venv_python)" || {
  echo "==> 错误: 未找到 python3，请先安装 Python 3.9+" >&2
  exit 1
}
if [[ "$VENV_PY" == python3 ]]; then
   read -r _maj _min < <(python3 -c 'import sys; print(sys.version_info[0], sys.version_info[1])' 2>/dev/null) || true
  if [[ "${_maj:-0}" -lt 3 ]] || [[ "${_maj:-0}" -eq 3 && "${_min:-0}" -lt 9 ]]; then
    echo "==> 错误: 当前 python3 为 ${_maj:-?}.${_min:-?}，需要 3.9+。请安装 python3.9/python3.10 等后重试。" >&2
    exit 1
  fi
fi

echo "==> 工作目录: $BACKEND_DIR"
echo "==> 使用端口: $PORT；venv Python: $VENV_PY"

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
  echo "==> 警告: 未找到 lsof，尝试 fuser 或 pkill"
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${PORT}/tcp" 2>/dev/null || true
  else
    pkill -f "uvicorn app:app.*--port ${PORT}" 2>/dev/null || true
  fi
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
  echo "==> 创建虚拟环境: $VENV_DIR ($VENV_PY -m venv)"
  "$VENV_PY" -m venv "$VENV_DIR"
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
