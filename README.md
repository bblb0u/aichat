# ChatGPT-style OpenAI API Chat

一个前后端分离的 ChatGPT 风格聊天项目。

- `frontend/`: 纯静态网页，打开后输入后端地址和访问密钥即可使用。
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
    - "change-me-login-key"

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

`server.access_keys` 是前端登录时填写的密钥；`providers[].api_key` 是后端调用上游 API 的密钥，不会发给浏览器。

### 2. Docker 运行后端

```bash
cd backend
docker build -t aichat .
docker run --rm -p 8000:8000 \
  -e CONFIG_PATH=/app/config.yaml \
  -v "$PWD/config.yaml:/app/config.yaml:ro" \
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

## 配置多个 API

`providers` 支持多个 OpenAI 兼容服务：

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
    models: ["custom-chat-model"]
    default_model: "custom-chat-model"
```

后端会调用：

```text
{base_url}/chat/completions
```

## 接口

- `GET /health` 健康检查
- `GET /api/providers` 获取可用提供方和模型，需要 `Authorization: Bearer <access_key>`
- `POST /api/chat/completions` 非流式聊天，需要 `Authorization: Bearer <access_key>`
- `POST /api/chat/stream` 流式聊天，需要 `Authorization: Bearer <access_key>`
