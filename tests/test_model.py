from foldwise import model
from foldwise.config import Node, Policy
from foldwise.extract import Extracted
from tests.fakes import FakeModel

TREE = {
    "~/Docs/Areas": Node("areas", {"~/Docs/Areas/Tax": Node("tax"), "~/Docs/Areas/Legal": Node("legal")}),
    "Projects": Node("code", {"~/Code/app": Node("app", dest="~/Code/app/_inbox"), "~/Code/lib": Node("lib")}),
    "~/Docs/Held": Node("held", hold=True),
}
TOP = ("~/Docs/Areas", "Projects", "~/Docs/Held")
AREAS = ("~/Docs/Areas/Tax", "~/Docs/Areas/Legal")
PROJ = ("~/Code/app", "~/Code/lib")


def test_meaningless_names():
    for stem in ("3f9a2c1be7d84f02a1c9", "a0c92436-02f2-4d8b-9890-8f68d7b0af0c", "image", "image (1)", "IMG_1234",
                 "unnamed", "Untitled"):
        assert model.meaningless(stem), stem
    for stem in ("invoice-2024", "logo", "Screenshot 2025-10-09", "beef"):
        assert not model.meaningless(stem), stem


def test_threshold_depends_on_model_count():
    assert model.threshold(Policy(), 1) == 0.85
    assert model.threshold(Policy(), 2) == 0.75


def test_state_and_question_shapes():
    assert model.state_for("a.pdf", Extracted("text", "meta")) == {"filename": "a.pdf", "metadata": "meta",
                                                                    "content": "text"}
    q = model.question(TREE["~/Docs/Areas"].children)
    assert q["c"]["type"] == "choice"
    assert q["c"]["criteria"] == {"~/Docs/Areas/Tax": "tax", "~/Docs/Areas/Legal": "legal"}


def test_agreeing_models_reach_a_leaf():
    m = {TOP: ("~/Docs/Areas", 0.9), AREAS: ("~/Docs/Areas/Tax", 0.8)}
    d = model.descend(TREE, {}, [FakeModel(m), FakeModel(m)], 0.75)
    assert d.dest == "~/Docs/Areas/Tax" and d.held is None and d.confidence == 0.8


def test_disagreement_and_low_confidence_hold():
    a = FakeModel({TOP: ("~/Docs/Areas", 0.9), AREAS: ("~/Docs/Areas/Tax", 0.9)})
    b = FakeModel({TOP: ("~/Docs/Areas", 0.9), AREAS: ("~/Docs/Areas/Legal", 0.9)})
    assert model.descend(TREE, {}, [a, b], 0.75).held == "models disagree"
    low = FakeModel({TOP: ("~/Docs/Areas", 0.6)})
    d = model.descend(TREE, {}, [low], 0.85)
    assert d.held == "low confidence" and d.dest is None


def test_group_levels_and_dest_override():
    m = FakeModel({TOP: ("Projects", 0.95), PROJ: ("~/Code/app", 0.95)})
    assert model.descend(TREE, {}, [m], 0.85).dest == "~/Code/app/_inbox"


def test_held_node():
    assert model.descend(TREE, {}, [FakeModel({TOP: ("~/Docs/Held", 0.99)})], 0.85).held == "held folder"


def test_load_models_without_checkpoints_returns_nothing(tmp_path):
    assert model.load_models(["v1", "v2"], tmp_path) == []
