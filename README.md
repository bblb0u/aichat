# AI Chat

一个自用或小团队使用的 ChatGPT 风格网页聊天工具。

前端负责聊天界面，后端负责登录、会话保存、模型列表和 API 转发。浏览器只需要知道后端地址和访问密钥，不直接接触上游 API Key。

## 核心逻辑

- 用访问密钥登录。每个访问密钥对应一个独立用户。
- 登录后后端签发 JWT，前端会保存登录状态，下次打开自动恢复。
- 聊天记录保存在后端 SQLite，不依赖浏览器本地历史。
- 不同访问密钥的会话和消息互相隔离。
- 前端只选择模型，不选择 API provider。
- 如果多个 provider 支持同一个模型，后端会按配置顺序自动尝试；前一个 provider 在开始输出前失败时，会切到下一个。

## 目录

```text
frontend/   静态网页前端
backend/    FastAPI 后端和 Dockerfile
```

## 准备配置

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
  jwt_secret: "replace-with-a-long-random-secret"
  jwt_expires_minutes: 43200
  data_path: "data/chat.db"
  cors_origins:
    - "*"

providers:
  - id: "openai"
    name: "OpenAI"
    base_url: "https://api.openai.com/v1"
    api_key: "sk-your-api-key"
    models:
      - "your-chat-model"
      - "your-fast-model"
    default_model: "your-chat-model"
```

配置含义：

- `server.access_keys`：用户登录前端时填写的密钥。一个密钥就是一个用户身份。
- `server.jwt_secret`：JWT 签名密钥。上线后不要随便改，改了会让已有登录状态失效。
- `server.jwt_expires_minutes`：登录有效期，默认示例是 30 天。
- `server.data_path`：SQLite 数据库路径，聊天历史保存在这里。
- `server.cors_origins`：允许访问后端的前端来源。自己用可以先保留 `*`，公开部署建议改成你的前端域名。
- `providers[].base_url`：OpenAI 兼容接口地址，不要带 `/chat/completions`。
- `providers[].api_key`：该 provider 的 API Key，只放在后端配置里。
- `providers[].models`：这个 provider 支持的模型名。
- `providers[].default_model`：前端首次打开时优先选中的模型。

## 配置多个 API

多个 provider 可以写在同一个 `providers` 列表里：

```yaml
providers:
  - id: "primary"
    name: "Primary API"
    base_url: "https://api.example-one.com/v1"
    api_key: "key-one"
    models: ["chat-model", "fast-model"]
    default_model: "chat-model"

  - id: "backup"
    name: "Backup API"
    base_url: "https://api.example-two.com/v1"
    api_key: "key-two"
    models: ["chat-model"]
    default_model: "chat-model"
```

当用户在前端选择 `chat-model` 时，后端会先请求 `Primary API`。如果它在开始返回内容前失败，会继续尝试 `Backup API`。

## 运行后端

### 使用 Docker 镜像

如果你已经把后端镜像推送到 Docker Hub，用实际镜像名替换下面的 `your-dockerhub-username/aichat:latest`：

```bash
cd backend
mkdir -p data

docker run -d \
  --name aichat-backend \
  -p 8000:8000 \
  -e CONFIG_PATH=/app/config.yaml \
  -v "$PWD/config.yaml:/app/config.yaml:ro" \
  -v "$PWD/data:/app/data" \
  your-dockerhub-username/aichat:latest
```

后端默认地址：

```text
http://localhost:8000
```

检查后端是否正常：

```bash
curl http://localhost:8000/health
```

返回下面内容表示后端已启动：

```json
{"status":"ok"}
```

### 从当前代码直接启动

如果还没有可用镜像，也可以直接启动后端：

```bash
cd backend
./run-local.sh
```

## 打开前端

可以使用已部署的前端：

```text
https://aichat-8sh.pages.dev
```

也可以直接打开本地文件：

```text
frontend/index.html
```

登录时填写：

- 后端地址：例如 `http://localhost:8000`
- 访问密钥：`backend/config.yaml` 里的 `server.access_keys` 之一

## 日常使用

- 左侧 `新对话` 创建新会话。
- 左侧会话列表可以切换历史会话并继续聊天。
- 顶部模型按钮用于选择模型。
- 点击 `退出` 会清除当前浏览器里的登录状态。
- 同一个访问密钥在不同浏览器登录，会看到同一份后端历史。
- 不同访问密钥登录，会看到各自独立的历史。

## 数据和备份

聊天历史保存在 `server.data_path` 指向的 SQLite 文件中。按上面的 Docker 命令运行时，数据库在：

```text
backend/data/chat.db
```

备份时保存这个文件即可。迁移到新机器时，把 `config.yaml` 和 `data/chat.db` 一起带过去，并保持 `jwt_secret` 不变。

## 环境变量覆盖

下面的环境变量会覆盖 `config.yaml` 里的同名服务端配置：

```text
ACCESS_KEYS            逗号分隔的访问密钥
CORS_ORIGINS           逗号分隔的允许来源
JWT_SECRET             JWT 签名密钥
JWT_EXPIRES_MINUTES    JWT 有效期分钟数
DATA_PATH              SQLite 数据库路径
CONFIG_PATH            配置文件路径
```

`providers` 仍然通过 `config.yaml` 配置。

## 常见问题

### 登录失败

检查：

- 后端地址是否能在浏览器访问。
- 填写的访问密钥是否存在于 `server.access_keys`。
- 修改配置后是否重启了后端。

### 前端没有模型

检查：

- `providers` 至少配置了一个 provider。
- 每个 provider 的 `models` 不是空列表。
- `default_model` 必须出现在同一个 provider 的 `models` 里。

### 聊天请求失败

检查：

- `base_url` 是否是 OpenAI 兼容接口根地址，例如 `https://api.example.com/v1`。
- `api_key` 是否有效。
- 选择的模型是否在某个 provider 的 `models` 里。
- provider 是否支持 `/chat/completions`。

### 历史记录不见了

检查：

- 是否换了访问密钥。不同访问密钥对应不同用户。
- Docker 是否挂载了 `/app/data`。没有挂载时，容器删除后数据库也会丢失。
- `DATA_PATH` 或 `server.data_path` 是否改到了另一个位置。

### 公网前端连不上后端

检查：

- 后端是否有公网可访问地址。
- HTTPS 前端最好连接 HTTPS 后端。
- `server.cors_origins` 是否允许你的前端域名，例如 `https://aichat-8sh.pages.dev`。
