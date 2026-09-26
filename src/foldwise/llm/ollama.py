"""Local Ollama server. Standard-library HTTP."""
import base64

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


class OllamaProvider:
    name = "ollama"

    def __init__(self, model: str | None = None, base_url: str = "http://localhost:11434", batch: int = 10):
        self.model, self.base_url, self.batch = model, base_url.rstrip("/"), batch

    def _model(self) -> str:
        if self.model:
            return self.model
        names = [m.get("name", "?") for m in base.get_json(f"{self.base_url}/api/tags", {}).get("models", [])]
        raise LLMError(f"set llm.ollama.model in taxonomy.yaml; pulled models: {', '.join(names) or 'none'}")

    def estimate(self, items: list[ReviewItem], leaves: dict[str, str]) -> str:
        return f"about {estimate_tokens(items, leaves):,} input tokens, {where(self.base_url)}"

    def suggest(self, items: list[ReviewItem], leaves: dict[str, str]) -> list[Suggestion]:
        model = self._model()
        keys = list(leaves)
        out: list[Suggestion] = []
        for chunk in batches(items, self.batch):
            for group in image_safe(chunk):
                user = {"role": "user", "content": render(group, leaves),
                        "images": [base64.standard_b64encode(it.image).decode() for it in group if it.image]}
                payload = {"model": model, "stream": False, "format": schema(keys),
                           "messages": [{"role": "system", "content": PROMPT}, user]}
                resp = base.post_json(f"{self.base_url}/api/chat", payload, {})
                out += parse(resp.get("message", {}).get("content", ""), [it.id for it in group], keys)
        return out
