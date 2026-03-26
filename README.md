# Token Monitor ✨

> 监控 MiniMax 和讯飞星辰 API 用量

## 项目结构

```
~/share/new/
├── backend/           # Flask API 服务
│   └── app.py         # 后端主程序
├── frontend/          # 前端静态页面
│   └── index.html    # 主页面
├── data/              # 数据存储（Cookie 等）
│   ├── minimax_cookies.json
│   └── xfyun_cookies.json
└── README.md
```

## 部署架构

```
                    ┌─────────────────┐
                    │   用户浏览器     │
                    │  (Web / 手机)   │
                    └────────┬────────┘
                             │ HTTP
                             ▼
┌─────────────┐     ┌─────────────────┐
│   Nginx     │────►│   Flask API     │
│  (静态资源) │     │   :5188         │
└─────────────┘     └────────┬────────┘
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
            MiniMax API           讯飞 API
```

## 快速启动

### 后端
```bash
cd ~/share/new/backend
pip install -r requirements.txt
python3 app.py
```

### 前端
直接用浏览器打开 `frontend/index.html`，或者部署到 Nginx。

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/status` | GET | 获取所有服务状态 |
| `/api/minimax` | GET | 获取 MiniMax 用量 |
| `/api/xfyun` | GET | 获取讯飞用量 |
| `/api/set-cookie` | POST | 设置 Cookie |
| `/api/login/status` | GET | 检查登录状态 |

## Cookie 管理

Cookie 存在 `data/` 目录下：
- `data/minimax_cookies.json`
- `data/xfyun_cookies.json`

Cookie 有效期：30分钟

### 手动设置 Cookie

```bash
# MiniMax
curl -X POST http://localhost:5188/api/set-cookie \
  -H "Content-Type: application/json" \
  -d '{"service":"minimax","cookies":"你的cookie"}'

# 讯飞
curl -X POST http://localhost:5188/api/set-cookie \
  -H "Content-Type: application/json" \
  -d '{"service":"xfyun","cookies":"你的cookie"}'
```

## 依赖

### 后端
```
Flask>=3.0.0
requests>=2.31.0
```

---

*由爱丽丝维护 ✨*
