import json
from pathlib import Path

import pytest
from rich.console import Console

from foldwise.config import Config, Node
from foldwise.extract import Extracted
from foldwise.llm import base
from foldwise.llm.ollama import OllamaProvider
from foldwise.llm.openai_compat import OpenAICompatProvider
from foldwise.plan import PlanItem
from foldwise.tui.review import llm_review

LEAVES = {"~/Docs/Tax": "taxes", "~/Docs/Photos": "photos"}
ANSWER = json.dumps({"suggestions": [{"id": 0, "dest": "~/Docs/Tax", "reason": "invoice"}]})


def items(tmp_path, with_image=False):
    (tmp_path / "shot.png").write_bytes(b"\x89PNG fake")
    return [base.ReviewItem(0, tmp_path / "a.pdf", "a.pdf", "", "invoice text"),
            base.ReviewItem(1, tmp_path / "shot.png", "shot.png", "1024x1024 px", "",
                            b"\x89PNG fake" if with_image else None, "image/png" if with_image else None)]


def test_schema_parse_and_render():
    s = base.schema(list(LEAVES))
    assert s["properties"]["suggestions"]["items"]["properties"]["dest"]["enum"] == [*LEAVES, "none"]
    text = json.dumps({"suggestions": [{"id": 0, "dest": "~/Docs/Tax", "reason": "invoice"},
                                       {"id": 1, "dest": "~/Docs/Made/Up", "reason": "?"}]})
    got = base.parse(text, [0, 1, 2], list(LEAVES))
    assert [(g.id, g.dest) for g in got] == [(0, "~/Docs/Tax"), (1, None), (2, None)]
    assert all(g.dest is None for g in base.parse("not json", [0], list(LEAVES)))
    assert '"filename": "a.pdf"' in base.render([base.ReviewItem(0, Path("a.pdf"), "a.pdf", "", "")], LEAVES)


def test_review_items_withhold_credentials_and_gate_images(tmp_path):
    (tmp_path / "p.png").write_bytes(b"img")
    (tmp_path / "k.txt").write_text("k")
    pairs = [(tmp_path / "p.png", Extracted("", "", "none")), (tmp_path / "k.txt", Extracted("x", sensitive=True))]
    sent, withheld = base.review_items(pairs, images=False)
    assert [i.filename for i in sent] == ["p.png"] and sent[0].image is None and withheld == [tmp_path / "k.txt"]
    sent, _ = base.review_items(pairs, images=True)
    assert sent[0].image == b"img" and sent[0].media_type == "image/png"


def test_review_items_survive_vanished_files(tmp_path):
    gone = tmp_path / "gone.png"
    pairs = [(gone, Extracted("", "", "none"))]
    sent, withheld = base.review_items(pairs, images=True)
    assert [i.filename for i in sent] == ["gone.png"] and sent[0].image is None and withheld == []


def test_image_safe_splits_one_request_per_image(tmp_path):
    both = items(tmp_path, True)  # [a.pdf (no image), shot.png (with image)]
    groups = list(base.image_safe(both))
    assert [[g.filename for g in grp] for grp in groups] == [["a.pdf"], ["shot.png"]]
    text_only = items(tmp_path)
    assert list(base.image_safe(text_only)) == [text_only]


def test_estimate_and_locality(tmp_path):
    # "image_attached": true renders one character shorter than false, so allow one token of rounding
    assert base.estimate_tokens(items(tmp_path, True), LEAVES) - base.estimate_tokens(items(tmp_path), LEAVES) >= 1599
    assert base.is_local("http://localhost:1234/v1") and base.is_local("http://127.0.0.1:11434")
    assert not base.is_local("https://api.example.com/v1")
    assert "locally" in OpenAICompatProvider(model="m").estimate(items(tmp_path), LEAVES)
    remote = OpenAICompatProvider(model="m", base_url="https://api.example.com/v1").estimate(items(tmp_path), LEAVES)
    assert "leaves this machine" in remote and "api.example.com" in remote


def test_lmstudio_openai_and_ollama_payloads(tmp_path, monkeypatch):
    sent = []

    def fake_post(url, payload, headers, timeout=180):
        sent.append((url, payload, headers))
        if url.endswith("/chat/completions"):
            return {"choices": [{"message": {"content": ANSWER}}]}
        return {"message": {"content": ANSWER}}

    monkeypatch.setattr(base, "post_json", fake_post)
    lmstudio = base.get_provider("lmstudio", {"lmstudio": {"model": "local-model"}})
    assert lmstudio.suggest(items(tmp_path, True), LEAVES)[0].dest == "~/Docs/Tax"
    url, payload, headers = sent[-1]
    assert url == "http://localhost:1234/v1/chat/completions" and "Authorization" not in headers
    assert payload["response_format"]["type"] == "json_schema"
    assert any(part.get("type") == "image_url" for part in payload["messages"][1]["content"])

    monkeypatch.setenv("MY_KEY", "secret-value")
    remote = base.get_provider("openai", {"openai": {"base_url": "https://llm.example.com/v1", "model": "m",
                                                     "api_key_env": "MY_KEY"}})
    remote.suggest(items(tmp_path), LEAVES)
    assert sent[-1][2]["Authorization"] == "Bearer secret-value"
    monkeypatch.delenv("MY_KEY")
    with pytest.raises(base.LLMError, match="MY_KEY"):
        remote.suggest(items(tmp_path), LEAVES)

    base.get_provider("ollama", {"ollama": {"model": "local-vision"}}).suggest(items(tmp_path, True), LEAVES)
    url, payload, _ = sent[-1]
    assert url == "http://localhost:11434/api/chat" and payload["stream"] is False and payload["messages"][1]["images"]


def test_missing_model_lists_what_the_server_has(monkeypatch):
    def fake_get(url, headers, timeout=10):
        if url.endswith("/api/tags"):
            return {"models": [{"name": "llava:7b"}, {"name": "qwen2.5vl:7b"}]}
        return {"data": [{"id": "loaded-model"}]}

    monkeypatch.setattr(base, "get_json", fake_get)
    with pytest.raises(base.LLMError, match="llava:7b, qwen2.5vl:7b"):
        OllamaProvider().suggest([], LEAVES)
    with pytest.raises(base.LLMError, match="loaded-model"):
        base.get_provider("lmstudio", {}).suggest([], LEAVES)


def test_provider_config_errors():
    with pytest.raises(base.LLMError, match="unknown provider"):
        base.get_provider("gemini", {})
    with pytest.raises(base.LLMError, match="base_url"):
        base.get_provider("openai", {"openai": {"model": "m"}})


class FakeProvider:
    name = "fake"

    def estimate(self, items, leaves):
        return "about 10 tokens, processed locally"

    def suggest(self, items, leaves):
        return [base.Suggestion(i.id, "~/Docs/Tax" if i.filename == "a.pdf" else None, "r") for i in items]


def test_llm_review_accept_and_decline(tmp_path):
    cfg = Config(inboxes=[], roots=[], sensitive_dest="~/S", review_dir="~/R",
                 tree={"~/Docs/Tax": Node("taxes"), "~/Docs/Photos": Node("photos")})
    held = [PlanItem(str(tmp_path / "a.pdf"), "", "hold", "low"), PlanItem(str(tmp_path / "b.pdf"), "", "hold", "low")]
    for h in held:
        Path(h.src).write_text("x")
    answers = iter(["a", "y"])
    quiet = Console(file=open("/dev/null", "w"))
    moves, rules = llm_review(held, cfg, FakeProvider(), lambda p: Extracted("text"), False, lambda q: True,
                              lambda q: next(answers), quiet)
    assert [m.dest.endswith("Docs/Tax/a.pdf") for m in moves] == [True]
    assert rules == []  # "a.pdf" has no word of 4+ letters
    assert llm_review(held, cfg, FakeProvider(), lambda p: Extracted("t"), False, lambda q: False, lambda q: "a",
                      quiet) == ([], [])
