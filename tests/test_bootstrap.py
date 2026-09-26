from pathlib import Path

from foldwise import bootstrap


def test_tilde(home):
    assert bootstrap.tilde(Path(home) / "Documents/x") == "~/Documents/x"
    assert bootstrap.tilde(Path("/opt/data")) == "/opt/data"


def test_build_tree_depth_repos_and_hidden(home, make):
    root = make({
        "Documents/Areas/Tax/2023/return.pdf": "x", "Documents/Areas/Tax/2023/deep/w2.pdf": "x",
        "Documents/Areas/Legal/nda.pdf": "x", "Documents/.cache/junk": "x",
        "Documents/Code/app/.git/HEAD": "x", "Documents/Code/app/src/main.py": "x",
    }, root=Path(home))
    tree = bootstrap.build_tree([root / "Documents"])
    assert set(tree) == {"~/Documents/Areas", "~/Documents/Code"}
    tax = tree["~/Documents/Areas"].children["~/Documents/Areas/Tax"]
    assert set(tax.children) == {"~/Documents/Areas/Tax/2023"}
    assert tax.children["~/Documents/Areas/Tax/2023"].children == {}  # depth 3 stops here
    assert tree["~/Documents/Code"].children["~/Documents/Code/app"].children == {}  # repos are leaves
    assert "return" in tax.desc


def test_describe_samples_names(make):
    root = make({"Invoices_2024/jan.pdf": "x", "Invoices_2024/feb.pdf": "x"})
    assert bootstrap.describe(root / "Invoices_2024") == "Invoices 2024: feb, jan"


def test_init_config_falls_back_to_para_and_proposes_rules(home, make):
    empty = Path(home) / "Empty"
    empty.mkdir()
    cfg = bootstrap.init_config([empty], [Path(home) / "Downloads"])
    assert set(cfg.tree) == {f"~/Empty/{k}" for k in bootstrap.PARA}
    assert cfg.sensitive_dest == "~/Empty/Sensitive" and cfg.review_dir == "~/Empty/Duplicate-Review"
    root = make({f"Docs/Clients/acme-brief-{i}.md": "x" for i in range(3)} | {"Docs/Other/misc.md": "x"},
                root=Path(home))
    cfg = bootstrap.init_config([root / "Docs"], [])
    assert any("acme" in r.pattern and r.dest == "~/Docs/Clients" for r in cfg.rules)
