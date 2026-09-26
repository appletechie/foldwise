"""Local-first LLM review. Only masked text is sent; files flagged as containing credentials are never sent."""
import json
import mimetypes
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from ..extract import IMAGE_EXT, Extracted

PROMPT = ("You help sort a person's files into their existing folders. For each file you get an id, its filename, "
          "metadata, and extracted text; some images are attached. Pick the single best folder key from the list, "
          'or "none" when no folder clearly fits. Keep each reason under 15 words.')
CONTENT_CHARS = 2000
MAX_IMAGE_BYTES = 4_000_000
IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
IMAGE_TOKENS = 1600
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class LLMError(RuntimeError):
    pass


@dataclass
class ReviewItem:
    id: int
    path: Path
    filename: str
    metadata: str
    content: str
    image: bytes | None = None
    media_type: str | None = None


@dataclass
class Suggestion:
    id: int
    dest: str | None
    reason: str


def review_items(pairs: list[tuple[Path, Extracted]], images: bool) -> tuple[list[ReviewItem], list[Path]]:
    sent, withheld = [], []
    for n, (path, ex) in enumerate(pairs):
        if ex.sensitive:
            withheld.append(path)
            continue
        # Files can vanish between sort and review; cache.read already returns empty Extracted
        # for those, but stat/read_bytes here still need guarding so one gone file cannot kill review.
        image = media_type = None
        if images and path.suffix.lower() in IMAGE_EXT:
            try:
                ok = path.stat().st_size <= MAX_IMAGE_BYTES
            except OSError:
                ok = False
            if ok:
                guessed = mimetypes.guess_type(path.name)[0]
                if guessed in IMAGE_TYPES:
                    try:
                        image, media_type = path.read_bytes(), guessed
                    except OSError:
                        image = media_type = None
        sent.append(ReviewItem(n, path, path.name, ex.metadata, ex.text[:CONTENT_CHARS], image, media_type))
    return sent, withheld


def schema(leaf_keys: list[str]) -> dict:
    suggestion = {"type": "object", "additionalProperties": False, "required": ["id", "dest", "reason"],
                  "properties": {"id": {"type": "integer"},
                                 "dest": {"type": "string", "enum": [*leaf_keys, "none"]},
                                 "reason": {"type": "string"}}}
    return {"type": "object", "additionalProperties": False, "required": ["suggestions"],
            "properties": {"suggestions": {"type": "array", "items": suggestion}}}


def render(items: list[ReviewItem], leaves: dict[str, str]) -> str:
    folders = "\n".join(f"- {k}: {v}" for k, v in leaves.items())
    files = json.dumps([{"id": i.id, "filename": i.filename, "metadata": i.metadata, "content": i.content,
                         "image_attached": i.image is not None} for i in items], ensure_ascii=False)
    return f"Folders:\n{folders}\n\nFiles:\n{files}"


def parse(text: str, ids: list[int], leaf_keys: list[str]) -> list[Suggestion]:
    try:
        rows = json.loads(text).get("suggestions", [])
    except (json.JSONDecodeError, AttributeError):
        rows = []
    by_id = {r.get("id"): r for r in rows if isinstance(r, dict)}
    out = []
    for i in ids:
        row = by_id.get(i, {})
        dest = row.get("dest")
        out.append(Suggestion(i, dest if dest in leaf_keys else None, str(row.get("reason", "no answer"))[:200]))
    return out


def estimate_tokens(items: list[ReviewItem], leaves: dict[str, str]) -> int:
    return (len(PROMPT) + len(render(items, leaves))) // 4 + IMAGE_TOKENS * sum(i.image is not None for i in items)


def batches(items: list[ReviewItem], size: int) -> Iterator[list[ReviewItem]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


def image_safe(chunk: list[ReviewItem]) -> Iterator[list[ReviewItem]]:
    """Split a batch so every item carrying an image gets its own request.

    Providers that attach images at the message level cannot otherwise tell the model
    which image belongs to which file, and a misattributed image becomes a confident
    wrong-folder suggestion. Items without images still go out as one batch first."""
    plain = [it for it in chunk if it.image is None]
    if plain:
        yield plain
    for it in chunk:
        if it.image is not None:
            yield [it]


def is_local(url: str) -> bool:
    return (urlparse(url).hostname or "") in LOCAL_HOSTS


def where(url: str) -> str:
    return "processed locally" if is_local(url) else f"sent to {urlparse(url).hostname}: file text leaves this machine"


def _request(req: urllib.request.Request, timeout: float) -> dict:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise LLMError(f"{req.full_url}: HTTP {e.code} {e.read()[:300]!r}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise LLMError(f"could not reach {req.full_url}: {e} (is the server running?)") from e


def post_json(url: str, payload: dict, headers: dict, timeout: float = 180) -> dict:
    return _request(urllib.request.Request(url, data=json.dumps(payload).encode(),
                                            headers={"Content-Type": "application/json", **headers}), timeout)


def get_json(url: str, headers: dict, timeout: float = 10) -> dict:
    return _request(urllib.request.Request(url, headers=headers), timeout)


def get_provider(name: str, settings: dict):
    options = dict(settings.get(name, {}))
    if name == "ollama":
        from .ollama import OllamaProvider
        return OllamaProvider(**options)
    from .openai_compat import OpenAICompatProvider
    if name == "lmstudio":
        return OpenAICompatProvider(name="lmstudio", **{"base_url": "http://localhost:1234/v1", **options})
    if name == "openai":
        if "base_url" not in options:
            raise LLMError("set llm.openai.base_url in taxonomy.yaml to your OpenAI-compatible endpoint")
        return OpenAICompatProvider(name="openai", **options)
    raise LLMError(f"unknown provider {name!r}: use ollama, lmstudio or openai")
