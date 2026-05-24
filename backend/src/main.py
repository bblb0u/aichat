import json
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any

import httpx
import jwt
from jwt import InvalidTokenError
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from . import storage
from .config import AppConfig, ProviderConfig, load_config


class Message(BaseModel):
    role: str
    content: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in {"system", "user", "assistant"}:
            raise ValueError("role must be system, user, or assistant")
        return value


class ChatRequest(BaseModel):
    provider: str | None = None
    model: str
    messages: list[Message]
    session_id: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, gt=0, le=32000)


class LoginRequest(BaseModel):
    access_key: str


class LoginResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_at: str
    user_id: str


class AuthUser(BaseModel):
    user_id: str
    auth_type: str


class SessionCreateRequest(BaseModel):
    id: str | None = None
    title: str = "新对话"


def create_app() -> FastAPI:
    config = load_config()
    app = FastAPI(title="Chat API Proxy")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.server.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def startup() -> None:
        storage.init_db()

    return app


app = create_app()


def jwt_secret(config: AppConfig) -> str:
    if config.server.jwt_secret:
        return config.server.jwt_secret

    material = "\n".join(config.server.access_keys)
    return sha256(f"chat-api-jwt:{material}".encode()).hexdigest()


def user_id_for_key(access_key: str) -> str:
    return sha256(access_key.encode()).hexdigest()[:16]


def create_jwt(access_key: str) -> LoginResponse:
    config = load_config()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=config.server.jwt_expires_minutes)
    user_id = user_id_for_key(access_key)
    payload = {
        "sub": user_id,
        "iat": datetime.now(timezone.utc),
        "exp": expires_at,
    }
    token = jwt.encode(payload, jwt_secret(config), algorithm="HS256")
    return LoginResponse(token=token, expires_at=expires_at.isoformat(), user_id=user_id)


def require_user(request: Request) -> AuthUser:
    config = load_config()
    auth_header = request.headers.get("authorization", "")
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    try:
        payload = jwt.decode(token, jwt_secret(config), algorithms=["HS256"])
        subject = payload.get("sub")
        if isinstance(subject, str) and subject:
            return AuthUser(user_id=subject, auth_type="jwt")
    except InvalidTokenError:
        pass

    # Backward compatibility for direct Bearer access key clients.
    if token in config.server.access_keys:
        return AuthUser(user_id=user_id_for_key(token), auth_type="access_key")

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid or expired token",
    )


def validate_access_key(access_key: str) -> str:
    token = access_key.strip()
    if not token or token not in load_config().server.access_keys:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid access key",
        )
    return token


def available_models() -> list[str]:
    models: list[str] = []
    for provider in load_config().providers:
        for model in provider.models:
            if model not in models:
                models.append(model)
    return models


def providers_for_chat(chat: ChatRequest) -> list[ProviderConfig]:
    if chat.provider:
        providers = [provider for provider in load_config().providers if provider.id == chat.provider]
        if not providers:
            raise HTTPException(status_code=404, detail="Provider not found")
        if chat.model not in providers[0].models:
            raise HTTPException(status_code=400, detail="Model is not allowed for provider")
        return providers

    providers = [provider for provider in load_config().providers if chat.model in provider.models]
    if not providers:
        raise HTTPException(status_code=404, detail="Provider not found")
    return providers


def build_payload(chat: ChatRequest, model: str, stream: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [message.model_dump() for message in chat.messages],
        "stream": stream,
    }
    if chat.temperature is not None:
        payload["temperature"] = chat.temperature
    if chat.max_tokens:
        payload["max_tokens"] = chat.max_tokens
    return payload


def chat_url(provider: ProviderConfig) -> str:
    return str(provider.base_url).rstrip("/") + "/chat/completions"


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/login")
async def login(login_request: LoginRequest) -> LoginResponse:
    access_key = validate_access_key(login_request.access_key)
    return create_jwt(access_key)


@app.get("/api/auth/me")
async def me(user: AuthUser = Depends(require_user)) -> dict[str, str]:
    return {"user_id": user.user_id, "auth_type": user.auth_type}


@app.get("/api/providers", dependencies=[Depends(require_user)])
async def providers() -> dict[str, Any]:
    return {
        "models": available_models(),
        "providers": [
            {
                "id": provider.id,
                "name": provider.name,
                "models": provider.models,
                "default_model": provider.default_model or provider.models[0],
            }
            for provider in load_config().providers
        ]
    }


@app.get("/api/sessions")
async def sessions(user: AuthUser = Depends(require_user)) -> dict[str, Any]:
    return {"sessions": storage.list_sessions(user.user_id)}


@app.post("/api/sessions")
async def create_chat_session(
    session_request: SessionCreateRequest,
    user: AuthUser = Depends(require_user),
) -> dict[str, Any]:
    session_id = session_request.id or sha256(f"{user.user_id}:{datetime.now(timezone.utc)}".encode()).hexdigest()
    session = storage.create_session(user.user_id, session_id, session_request.title.strip() or "新对话")
    return {"session": session}


@app.get("/api/sessions/{session_id}")
async def session_detail(session_id: str, user: AuthUser = Depends(require_user)) -> dict[str, Any]:
    session = storage.get_session(user.user_id, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": session, "messages": storage.list_messages(user.user_id, session_id)}


@app.delete("/api/sessions/{session_id}")
async def remove_session(session_id: str, user: AuthUser = Depends(require_user)) -> dict[str, str]:
    storage.delete_session(user.user_id, session_id)
    return {"status": "ok"}


async def request_completion(chat: ChatRequest, provider: ProviderConfig) -> dict[str, Any]:
    payload = build_payload(chat, chat.model, stream=False)

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            chat_url(provider),
            headers={
                "Authorization": f"Bearer {provider.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    return response.json()


@app.post("/api/chat/completions")
async def chat_completion(chat: ChatRequest, user: AuthUser = Depends(require_user)) -> dict[str, Any]:
    errors: list[str] = []

    for provider in providers_for_chat(chat):
        try:
            data = await request_completion(chat, provider)
            persist_completion(chat, user, data)
            return data
        except (HTTPException, httpx.HTTPError) as exc:
            errors.append(f"{provider.name}: {exc}")

    raise HTTPException(status_code=502, detail=f"All providers failed: {'; '.join(errors)}")


async def stream_provider(chat: ChatRequest, provider: ProviderConfig) -> AsyncIterator[bytes]:
    payload = build_payload(chat, chat.model, stream=True)

    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST",
            chat_url(provider),
            headers={
                "Authorization": f"Bearer {provider.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        ) as response:
            if response.status_code >= 400:
                body = await response.aread()
                message = body.decode(errors="replace").replace("\n", " ")
                raise RuntimeError(message)

            async for chunk in response.aiter_bytes():
                yield chunk


async def stream_with_fallback(chat: ChatRequest, providers: list[ProviderConfig]) -> AsyncIterator[bytes]:
    errors: list[str] = []

    for provider in providers:
        yielded = False
        try:
            async for chunk in stream_provider(chat, provider):
                yielded = True
                yield chunk
            return
        except (RuntimeError, httpx.HTTPError) as exc:
            if yielded:
                message = f"{provider.name}: upstream stream interrupted: {exc}"
                yield b"event: error\n"
                yield f"data: {json.dumps({'error': {'message': message}})}\n\n".encode()
                return
            errors.append(f"{provider.name}: {exc}")

    message = f"All providers failed: {'; '.join(errors)}"
    yield b"event: error\n"
    yield f"data: {json.dumps({'error': {'message': message}})}\n\n".encode()


async def persistent_stream(chat: ChatRequest, user: AuthUser, providers: list[ProviderConfig]) -> AsyncIterator[bytes]:
    assistant_content = ""
    buffer = ""

    async for chunk in stream_with_fallback(chat, providers):
        text = chunk.decode(errors="ignore")
        buffer += text
        delta, buffer = extract_content_from_sse_buffer(buffer)
        assistant_content += delta
        yield chunk

    delta, _ = extract_content_from_sse_buffer(buffer + "\n\n")
    assistant_content += delta

    if chat.session_id and assistant_content:
        storage.add_message(user.user_id, chat.session_id, "assistant", assistant_content)


def persist_user_message(chat: ChatRequest, user: AuthUser) -> None:
    if not chat.session_id or not chat.messages:
        return

    title = "新对话"
    first_user_message = next((message.content for message in chat.messages if message.role == "user"), "")
    if first_user_message:
        title = first_user_message[:28]

    session = storage.ensure_session(user.user_id, chat.session_id, title)
    latest_user_message = next((message for message in reversed(chat.messages) if message.role == "user"), None)
    if latest_user_message:
        storage.add_message(user.user_id, chat.session_id, "user", latest_user_message.content)
        if session["title"] == "新对话":
            storage.update_session_title(user.user_id, chat.session_id, latest_user_message.content[:28])


def persist_completion(chat: ChatRequest, user: AuthUser, data: dict[str, Any]) -> None:
    if not chat.session_id:
        return
    persist_user_message(chat, user)
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if content:
        storage.add_message(user.user_id, chat.session_id, "assistant", content)


def extract_content_from_sse_buffer(buffer: str) -> tuple[str, str]:
    events = buffer.split("\n\n")
    remainder = events.pop() or ""
    content = ""
    for event_text in events:
        for line in event_text.splitlines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                parsed = json.loads(data)
            except json.JSONDecodeError:
                continue
            content += parsed.get("choices", [{}])[0].get("delta", {}).get("content", "")
            content += parsed.get("choices", [{}])[0].get("message", {}).get("content", "")
    return content, remainder


@app.post("/api/chat/stream")
async def chat_stream(chat: ChatRequest, user: AuthUser = Depends(require_user)) -> StreamingResponse:
    providers = providers_for_chat(chat)
    persist_user_message(chat, user)
    return StreamingResponse(persistent_stream(chat, user, providers), media_type="text/event-stream")
