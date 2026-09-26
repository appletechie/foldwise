import random
from collections import Counter

import pytest

from foldwise.config import Config, Node
from foldwise.train import dataset
from foldwise.train.evaluate import evaluate
from tests.fakes import FakeModel


def cfg_for(root) -> Config:
    return Config(inboxes=[], roots=[str(root / "Docs"), str(root / "Code")], sensitive_dest="~/S", review_dir="~/R",
                  tree={str(root / "Docs/Big"): Node("big"), str(root / "Docs/Small"): Node("small"),
                        str(root / "Code/app"): Node("app")})


def build(make):
    spec = {f"Docs/Big/f{i:03}.txt": str(i) for i in range(100)}
    spec |= {"Docs/Small/a.txt": "a", "Docs/Small/b.txt": "b"}
    spec |= {"Code/app/.git/HEAD": "h", "Code/app/src/main.py": "p", "Code/app/README.md": "r",
             **{f"Code/app/docs/d{i}.md": str(i) for i in range(12)}}
    return make(spec)


def test_gather_caps_folders_and_repos(make):
    root = build(make)
    files = dataset.gather(cfg_for(root), random.Random(1))
    per_folder = Counter(f.parent.name if "Code" not in f.parts else "repo" for f in files)
    assert per_folder["Big"] == 60 and per_folder["Small"] == 2 and per_folder["repo"] == 8
    assert all(f.suffix != ".py" for f in files)
    assert root / "Code/app/README.md" in files  # shallowest repo docs first


def test_frozen_split_is_created_once_and_reused(make, tmp_path):
    root = build(make)
    cfg = cfg_for(root)
    files = dataset.gather(cfg, random.Random(1))
    train, test = dataset.frozen_split(files, cfg.tree, tmp_path / "test_set.json", random.Random(1))
    assert len(test) == 12 + 1 and not set(train) & set(test)  # 60//5 from Big, 8//5 from the repo, none from Small
    (root / "Docs/Big/new.txt").write_text("new")
    train2, test2 = dataset.frozen_split(files + [root / "Docs/Big/new.txt"], cfg.tree, tmp_path / "test_set.json",
                                         random.Random(99))
    assert test2 == test and root / "Docs/Big/new.txt" in train2


def test_variant_and_oversampling(make):
    root = build(make)
    cfg = cfg_for(root)
    rng = random.Random(3)
    state = {"filename": "invoice.pdf", "metadata": "", "content": "text"}
    for _ in range(20):
        v = dataset.variant(state, rng)
        assert (v["content"] == "" and v["filename"] == "invoice.pdf") or \
               (v["content"] == "text" and v["filename"].endswith(".pdf") and v["filename"] != "invoice.pdf")
    small = [root / "Docs/Small/a.txt", root / "Docs/Small/b.txt"]
    states = {f: {"filename": f.name, "metadata": "", "content": f.read_text()} for f in small}
    pairs = dataset.training_states(small, states, cfg.tree, rng, min_per_leaf=8, share=0.0)
    assert len(pairs) == 8


def test_balance(make):
    root = build(make)
    cfg = cfg_for(root)
    assert dataset.balance(dataset.gather(cfg, random.Random(1)), cfg.tree) == Counter(Big=60, app=8, Small=2)


def test_evaluate_metrics(make):
    root = build(make)
    cfg = cfg_for(root)
    keys = tuple(cfg.tree)
    files = [root / "Docs/Big/f000.txt", root / "Docs/Small/a.txt"]
    states = {f: {} for f in files}
    always_big = FakeModel({keys: (str(root / "Docs/Big"), 0.9)})
    result = evaluate([always_big], files, states, cfg.tree, 0.85)
    assert result["accuracy"] == 0.5 and result["auto_share"] == 1.0 and result["auto_precision"] == 0.5


def test_evaluate_without_models_raises(make):
    root = build(make)
    cfg = cfg_for(root)
    files = [root / "Docs/Big/f000.txt"]
    states = {f: {} for f in files}
    with pytest.raises(ValueError, match="no models"):
        evaluate([], files, states, cfg.tree, 0.85)


class FakeTok:
    mask_token, mask_token_id, cls_token_id, sep_token_id = "«", 1, 2, 3

    def __call__(self, text, add_special_tokens=False, truncation=False, max_length=None):
        ids = [4 + (sum(map(ord, w)) % 500) for w in text.split()]
        return {"input_ids": ids[:max_length] if truncation else ids}


def test_items_for_builds_one_decision_per_level(make):
    root = build(make)
    cfg = cfg_for(root)
    f = root / "Docs/Big/f000.txt"
    items = dataset.items_for([(f, {"filename": f.name, "metadata": "", "content": "0"})], cfg.tree, FakeTok(), 512,
                              256)
    assert len(items) == 1 and items[0]["label"] == 0 and abs(sum(items[0]["target"]) - 1) < 1e-9
