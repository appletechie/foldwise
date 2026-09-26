"""Real training smoke test: downloads the laya checkpoint (~1.6 GB). Run with: pytest -m slow"""
import json
import random
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow


def test_one_tiny_epoch_saves_a_loadable_model(tmp_path):
    import torch
    from huggingface_hub import snapshot_download
    from laya import Agent
    from laya.agent import _fix_tokenizer_config
    from transformers import AutoTokenizer

    from foldwise.config import Node
    from foldwise.train import dataset, loop

    base = Path(snapshot_download("convaiinnovations/laya",
                                  allow_patterns=["encoder/*", "tokenizer/*", "*.json", "*.safetensors"]))
    _fix_tokenizer_config(str(base))
    tok = AutoTokenizer.from_pretrained(str(base / "tokenizer"))
    cfg = json.loads((base / "rl_agent_config.json").read_text()) | {"head_max_len": 256}
    tree = {str(tmp_path / "Tax"): Node("taxes, invoices"), str(tmp_path / "Photos"): Node("photos, images")}
    pairs = [(tmp_path / "Tax" / f"invoice-{i}.pdf", {"filename": f"invoice-{i}.pdf", "metadata": "",
                                                        "content": "invoice total due"}) for i in range(4)]
    pairs += [(tmp_path / "Photos" / f"beach-{i}.jpg", {"filename": f"beach-{i}.jpg", "metadata": "4032x3024 px",
                                                        "content": ""}) for i in range(4)]
    items = dataset.items_for(pairs, tree, tok, cfg["max_len"], cfg["head_max_len"])
    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    out = tmp_path / "model"
    loop.train_model(items[2:], items[:2] * 5, base, cfg, tok, device, out, random.Random(0), epochs=1, micro_batch=2,
                     grad_accum=1)
    assert (out / "rl_agent_config.json").exists() and (out / "model.safetensors").exists()
    Agent(str(out), device=device)
