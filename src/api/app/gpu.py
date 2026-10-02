"""GPU 서버(관문) 호출: 질문 임베딩(BGE-M3)과 답변 생성(Qwen3-32B) 스트리밍.

관문(infra/gpu_server/gateway.py)은 Cloudflare 임시 터널 때문에 스트리밍을 SSE 대신 NDJSON(한 줄에 JSON 하나)으로 보낸다.
환경변수: GPU_URL(터널 주소), GPU_API_KEY(GPU 서버 ~/llm-serve/.api_key 내용)
"""
import json
import os
from typing import AsyncIterator

import httpx

EMBED_MODEL = "bge-m3"
LLM_MODEL = "qwen3-32b"
# 연결 5초, 다음 조각까지 최대 60초 (긴 근거를 읽는 첫 조각이 가장 오래 걸린다)
TIMEOUT = httpx.Timeout(60, connect=5)


class GpuError(RuntimeError):
    pass


def _config() -> tuple[str, dict]:
    url, key = os.getenv("GPU_URL", "").rstrip("/"), os.getenv("GPU_API_KEY", "")
    if not url or not key:
        raise GpuError("GPU_URL·GPU_API_KEY가 설정되지 않았습니다")
    return url, {"Authorization": f"Bearer {key}"}


async def embed(text: str) -> list[float]:
    url, headers = _config()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(f"{url}/v1/embeddings", headers=headers, json={"model": EMBED_MODEL, "input": [text]})
    if r.status_code != 200:
        raise GpuError(f"임베딩 실패 {r.status_code}")
    return r.json()["data"][0]["embedding"]


async def chat_stream(messages: list[dict], max_tokens: int, temperature: float) -> AsyncIterator[str]:
    """답변 조각(content)을 차례로 내놓는다. Qwen3의 생각 과정 출력은 끈다."""
    url, headers = _config()
    body = {"model": LLM_MODEL, "messages": messages, "stream": True, "max_tokens": max_tokens,
            "temperature": temperature, "chat_template_kwargs": {"enable_thinking": False}}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        async with client.stream("POST", f"{url}/v1/chat/completions", headers=headers, json=body) as r:
            if r.status_code != 200:
                raise GpuError(f"생성 실패 {r.status_code}")
            async for line in r.aiter_lines():
                if not line.strip():
                    continue
                choice = json.loads(line)["choices"][0]
                if text := choice.get("delta", {}).get("content"):
                    yield text
