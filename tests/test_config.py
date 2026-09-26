from pathlib import Path

from foldwise import config, paths
from foldwise.config import Config, Node, Rule


def sample() -> Config:
    return Config(
        inboxes=["~/Downloads"], roots=["~/Documents"],
        sensitive_dest="~/Documents/Sensitive", review_dir="~/Documents/Review",
        tree={
            "~/Documents/Areas": Node("areas", {"~/Documents/Areas/Tax": Node("taxes")}),
            "Client work": Node("grouping", {"~/Documents/Clients/Acme": Node("acme")}),
        },
        rules=[Rule("name", r"(?i)invoice", "~/Documents/Areas/Tax")],
    )


def test_paths_follow_foldwise_home(home):
    assert paths.config_file() == home / "fw" / "config" / "taxonomy.yaml"
    assert paths.sub("plans").is_dir()
    assert paths.sub("plans").parent == home / "fw" / "state"


def test_round_trip(home):
    f = paths.config_file()
    config.save(sample(), f)
    loaded = config.load(f)
    assert loaded == sample()
    assert "~/Documents/Areas/Tax" in f.read_text()


def test_validate_flags_wide_nodes_bad_regex_and_empty_groups():
    cfg = sample()
    cfg.tree["~/Documents/Wide"] = Node("wide", {f"~/Documents/Wide/{i}": Node(str(i)) for i in range(9)})
    cfg.tree["Empty group"] = Node("nothing under it")
    cfg.rules.append(Rule("name", "([unclosed", "~/x"))
    cfg.rules.append(Rule("colour", "x", "~/x"))
    problems = "\n".join(config.validate(cfg))
    assert "9 children" in problems
    assert "Empty group" in problems
    assert "([unclosed" in problems
    assert "colour" in problems
    assert config.validate(sample()) == []


def test_label_path_walks_groups(home):
    tree = sample().tree
    f = Path(home) / "Documents/Clients/Acme/brief.pdf"
    assert config.label_path(tree, f) == ["Client work", "~/Documents/Clients/Acme"]
    assert config.label_path(tree, Path(home) / "Documents/Areas/Tax/2024.pdf") == ["~/Documents/Areas",
                                                                                     "~/Documents/Areas/Tax"]
    assert config.label_path(tree, Path(home) / "Elsewhere/x.pdf") == []


def test_is_group_and_expand(home):
    assert config.is_group("Client work")
    assert not config.is_group("~/Documents")
    assert not config.is_group("/abs/path")
    assert config.expand("~/Documents") == Path(home) / "Documents"
