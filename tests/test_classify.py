from foldwise.classify import Context, decide, filed_index
from foldwise.config import Config, Node, Rule
from foldwise.extract import Extracted
from tests.fakes import FakeModel


def cfg_for(root) -> Config:
    return Config(
        inboxes=[str(root / "Downloads")], roots=[str(root / "Docs")],
        sensitive_dest=str(root / "Docs/Sensitive"), review_dir=str(root / "Docs/Review"),
        protect=[str(root / "Docs/Case")],
        tree={str(root / "Docs/Tax"): Node("tax"), str(root / "Code/app"): Node("app")},
        rules=[Rule("name", r"(?i)tax return", str(root / "Docs/Tax"))],
    )


def ctx(cfg, models=(), filed=None):
    return Context(cfg, list(models), filed or {})


def test_order_protected_duplicate_secret_rule_name_model(make):
    root = make({"Docs/Case/evidence.png": b"e", "Docs/Tax/old.pdf": b"same bytes", "Downloads/copy.pdf": b"same bytes",
                 "Downloads/keys.txt": b"k", "Downloads/2024 Tax Return.pdf": b"t",
                 "Downloads/3f9a2c1be7d84f02a1c9.png": b"p", "Downloads/notes.txt": b"n"})
    cfg = cfg_for(root)
    incoming = [root / "Downloads" / n for n in ("copy.pdf", "keys.txt", "2024 Tax Return.pdf",
                                                 "3f9a2c1be7d84f02a1c9.png", "notes.txt")]
    c = ctx(cfg, filed=filed_index(cfg, incoming))
    assert decide(root / "Docs/Case/evidence.png", Extracted(), c).action == "skip"
    dup = decide(root / "Downloads/copy.pdf", Extracted(), c)
    assert dup.action == "move" and dup.dest == root / "Docs/Review" and "old.pdf" in dup.reason
    secret = decide(root / "Downloads/keys.txt", Extracted(sensitive=True), c)
    assert secret.dest == root / "Docs/Sensitive" and "credential" in secret.reason
    assert decide(root / "Downloads/2024 Tax Return.pdf", Extracted(), c).dest == root / "Docs/Tax"
    assert decide(root / "Downloads/3f9a2c1be7d84f02a1c9.png", Extracted(), c).reason == "meaningless name"
    no_model = decide(root / "Downloads/notes.txt", Extracted(), c)
    assert no_model.action == "hold" and "foldwise train" in no_model.reason


def test_duplicates_within_one_batch(make):
    root = make({"Downloads/a.pdf": b"x", "Downloads/a (1).pdf": b"x"})
    c = ctx(cfg_for(root))
    assert decide(root / "Downloads/a.pdf", Extracted(), c).action == "hold"
    second = decide(root / "Downloads/a (1).pdf", Extracted(), c)
    assert second.action == "move" and second.dest == root / "Docs/Review"


def test_model_moves_and_repo_destinations_hold(make):
    root = make({"Downloads/q3-numbers.xlsx": b"q", "Code/app/.git/HEAD": b"h"})
    cfg = cfg_for(root)
    keys = (str(root / "Docs/Tax"), str(root / "Code/app"))
    to_tax = FakeModel({keys: (str(root / "Docs/Tax"), 0.9)})
    moved = decide(root / "Downloads/q3-numbers.xlsx", Extracted(), ctx(cfg, [to_tax, to_tax]))
    assert moved.action == "move" and moved.dest == root / "Docs/Tax" and moved.reason == "model"
    to_repo = FakeModel({keys: (str(root / "Code/app"), 0.95)})
    held = decide(root / "Downloads/q3-numbers.xlsx", Extracted(), ctx(cfg, [to_repo]))
    assert held.action == "hold" and "git repo" in held.reason


def test_filed_index_ignores_the_incoming_files_themselves(make):
    root = make({"Docs/Tax/a.pdf": b"one", "Downloads/b.pdf": b"two"})
    idx = filed_index(cfg_for(root), [root / "Downloads/b.pdf"])
    # a.pdf is filed and size-matches b.pdf, so it is indexed; the incoming file itself never is
    assert list(idx.values()) == [root / "Docs/Tax/a.pdf"]
