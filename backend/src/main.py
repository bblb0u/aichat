import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from .config import ProviderConfig, get_provider, load_config


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
    provider: str
    model: str | None = None
    messages: list[Message]
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, gt=0, le=32000)


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

    return app


app = create_app()


def require_access_key(request: Request) -> None:
    auth_header = request.headers.get("authorization", "")
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    if token not in load_config().server.access_keys:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid access key",
        )


def resolve_provider(chat: ChatRequest) -> tuple[ProviderConfig, str]:
    provider = get_provider(chat.provider)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    model = chat.model or provider.default_model or provider.models[0]
    if model not in provider.models:
        raise HTTPException(status_code=400, detail="Model is not allowed for provider")

    return provider, model


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


@app.get("/api/providers", dependencies=[Depends(require_access_key)])
async def providers() -> dict[str, Any]:
    return {
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


@app.post("/api/chat/completions", dependencies=[Depends(require_access_key)])
async def chat_completion(chat: ChatRequest) -> dict[str, Any]:
    provider, model = resolve_provider(chat)
    payload = build_payload(chat, model, stream=False)

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            response = await client.post(
                chat_url(provider),
                headers={
                    "Authorization": f"Bearer {provider.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Upstream request failed: {exc}") from exc

    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    return response.json()


async def stream_upstream(chat: ChatRequest, provider: ProviderConfig, model: str) -> AsyncIterator[bytes]:
    payload = build_payload(chat, model, stream=True)

    async with httpx.AsyncClient(timeout=None) as client:
        try:
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
                    yield b"event: error\n"
                    yield f"data: {json.dumps({'error': {'message': message}})}\n\n".encode()
                    return

                async for chunk in response.aiter_bytes():
                    yield chunk
        except httpx.HTTPError as exc:
            yield b"event: error\n"
            yield f"data: {json.dumps({'error': {'message': f'Upstream request failed: {exc}'}})}\n\n".encode()


@app.post("/api/chat/stream", dependencies=[Depends(require_access_key)])
async def chat_stream(chat: ChatRequest) -> StreamingResponse:
    provider, model = resolve_provider(chat)
    return StreamingResponse(stream_upstream(chat, provider, model), media_type="text/event-stream")
