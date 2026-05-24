# ChatGPT-style OpenAI API Chat

一个前后端分离的 ChatGPT 风格聊天项目。

- `frontend/`: 纯静态网页，打开后输入后端地址和访问密钥即可使用，会保存登录状态并从后端恢复会话记录。
- `backend/`: FastAPI 后端，支持 Docker 部署，通过外置 `config.yaml` 配置多个 OpenAI 兼容 API 提供方。

## 快速开始

### 1. 配置后端

复制配置示例：

```bash
cp backend/config.example.yaml backend/config.yaml
```

编辑 `backend/config.yaml`：

```yaml
server:
  access_keys:
    - "user-one-login-key"
    - "user-two-login-key"
  jwt_secret: "change-me-jwt-secret"
  jwt_expires_minutes: 43200
  data_path: "data/chat.db"

providers:
  - id: "openai"
    name: "OpenAI"
    base_url: "https://api.openai.com/v1"
    api_key: "sk-..."
    models:
      - "gpt-5.5"
      - "gpt-5.4-mini"
    default_model: "gpt-5.5"
```

`server.access_keys` 是前端登录时填写的密钥。每个密钥会映射成一个独立用户，前端会按用户隔离本地会话记录。

`jwt_secret` 用于签发登录后的 JWT，生产环境建议通过 `JWT_SECRET` 环境变量设置一个稳定随机值。`providers[].api_key` 是后端调用上游 API 的密钥，不会发给浏览器。

`data_path` 是后端保存用户会话和消息的 SQLite 数据库路径。不同访问密钥对应不同用户，历史记录会按用户隔离。

### 2. Docker 运行后端

```bash
cd backend
docker build -t aichat .
docker run --rm -p 8000:8000 \
  -e CONFIG_PATH=/app/config.yaml \
  -v "$PWD/config.yaml:/app/config.yaml:ro" \
  -v "$PWD/data:/app/data" \
  aichat
```

默认后端地址：

```text
http://localhost:8000
```

### 3. 打开前端

直接用浏览器打开：

```text
frontend/index.html
```

登录时填写：

- 后端地址：`http://localhost:8000`
- 密钥：`backend/config.yaml` 里的 `server.access_keys` 之一

## 本地开发

后端：

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

也可以直接运行脚本：

```bash
cd backend
./run-local.sh
```

前端是静态文件，可直接打开，也可以用任意静态服务器托管 `frontend/`。

## 登录和会话

- 前端用访问密钥登录后，后端会签发 JWT。
- 前端会保存 JWT，下次打开自动恢复登录状态。
- 同一个后端里，不同访问密钥对应不同用户，会话记录互相隔离。
- 会话记录保存在后端 SQLite，支持新会话、切换旧会话、继续之前的对话。

## 配置多个 API

`providers` 支持多个 OpenAI 兼容服务。前端只选择模型，不选择 API；后端会按配置顺序选择支持该模型的 provider。如果前一个 provider 在开始输出前失败，会自动尝试下一个。

```yaml
providers:
  - id: "openai"
    name: "OpenAI"
    base_url: "https://api.openai.com/v1"
    api_key: "sk-..."
    models: ["gpt-5.5", "gpt-5.4-mini"]
    default_model: "gpt-5.5"

  - id: "custom"
    name: "Custom API"
    base_url: "https://example.com/v1"
    api_key: "your-key"
    models: ["gpt-5.5", "custom-chat-model"]
    default_model: "gpt-5.5"
```

后端会调用：

```text
{base_url}/chat/completions
```

## 接口

- `GET /health` 健康检查
- `POST /api/auth/login` 用访问密钥换取 JWT
- `GET /api/auth/me` 获取当前登录用户
- `GET /api/providers` 获取可用模型，需要 `Authorization: Bearer <jwt>`
- `GET /api/sessions` 获取当前用户的会话列表
- `POST /api/sessions` 创建新会话
- `GET /api/sessions/{session_id}` 获取会话和消息
- `DELETE /api/sessions/{session_id}` 删除会话
- `POST /api/chat/completions` 非流式聊天，需要 `Authorization: Bearer <jwt>`
- `POST /api/chat/stream` 流式聊天，需要 `Authorization: Bearer <jwt>`

## Docker 镜像

GitHub Actions 会把后端镜像推送到 Docker Hub，支持 `linux/amd64` 和 `linux/arm64`：

```text
<DOCKERHUB_USERNAME>/aichat:latest
<DOCKERHUB_USERNAME>/aichat:YYYYMMDD
```
