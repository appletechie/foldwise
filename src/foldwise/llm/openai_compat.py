"""LM Studio, or any OpenAI-compatible endpoint (vLLM, llama.cpp server, hosted APIs). Standard-library HTTP."""
import base64
import os

from . import base
from .base import (
    PROMPT,
    LLMError,
    ReviewItem,
    Suggestion,
    batches,
    estimate_tokens,
    image_safe,
    parse,
    render,
    schema,
    where,
)


class OpenAICompatProvider:
    def __init__(self, name: str = "openai", model: str | None = None, base_url: str = "http://localhost:1234/v1",
                 api_key_env: str | None = None, batch: int = 20):
        self.name, self.model, self.base_url = name, model, base_url.rstrip("/")
        self.api_key_env, self.batch = api_key_env, batch

    def _headers(self) -> dict:
        if not self.api_key_env:
            return {}
        key = os.environ.get(self.api_key_env)
        if not key:
            raise LLMError(f"set {self.api_key_env} (named by llm.{self.name}.api_key_env) to use {self.base_url}")
        return {"Authorization": f"Bearer {key}"}

    def _model(self) -> str:
        if self.model:
            return self.model
        names = [m.get("id", "?") for m in base.get_json(f"{self.base_url}/models", self._headers()).get("data", [])]
        raise LLMError(f"set llm.{self.name}.model in taxonomy.yaml; the server has: {', '.join(names) or 'none'}")

    def estimate(self, items: list[ReviewItem], leaves: dict[str, str]) -> str:
        return f"about {estimate_tokens(items, leaves):,} input tokens, {where(self.base_url)}"

    def suggest(self, items: list[ReviewItem], leaves: dict[str, str]) -> list[Suggestion]:
        headers, model = self._headers(), self._model()
        keys = list(leaves)
        out: list[Suggestion] = []
        for chunk in batches(items, self.batch):
            for group in image_safe(chunk):
                parts: list[dict] = [{"type": "text", "text": render(group, leaves)}]
                for it in group:
                    if it.image:
                        data = base64.standard_b64encode(it.image).decode()
                        parts.append({"type": "image_url",
                                      "image_url": {"url": f"data:{it.media_type};base64,{data}"}})
                payload = {"model": model,
                           "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": parts}],
                           "response_format": {"type": "json_schema",
                                               "json_schema": {"name": "suggestions", "strict": True,
                                                               "schema": schema(keys)}}}
                resp = base.post_json(f"{self.base_url}/chat/completions", payload, headers)
                out += parse(resp["choices"][0]["message"]["content"] or "", [it.id for it in group], keys)
        return out
