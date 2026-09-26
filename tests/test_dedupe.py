from foldwise import dedupe


def build(make):
    return make({
        "Logos/logo.png": b"A", "Logos/logo (1).png": b"A", "Downloads-2026-07-07/logo.png": b"A",
        "Sensitive/key.txt": b"B", "Notes/key.txt": b"B",
        "Locked/x.txt": b"C", "Locked/y.txt": b"C",
        "Solo/one.txt": b"D", "Empty/a.txt": b"", "Empty/b.txt": b"",
    })


def test_groups_pick_the_best_keeper(make):
    root = build(make)
    files = [p for p in root.rglob("*") if p.is_file()]
    found = {(k.parent.name, k.name): sorted(f"{f.parent.name}/{f.name}" for f in v)
             for k, v in dedupe.groups(files, [root / "Sensitive", root / "Locked"])}
    assert found == {
        ("Logos", "logo.png"): ["Downloads-2026-07-07/logo.png", "Logos/logo (1).png"],
        ("Sensitive", "key.txt"): ["Notes/key.txt"],
    }


def test_only_size_collisions_are_hashed(make, monkeypatch):
    root = make({"a.txt": b"1", "b.txt": b"22", "c.txt": b"333", "d.txt": b"333"})
    hashed = []
    real = dedupe.sha256
    monkeypatch.setattr(dedupe, "sha256", lambda p: hashed.append(p.name) or real(p))
    dedupe.groups([root / n for n in ("a.txt", "b.txt", "c.txt", "d.txt")], [])
    assert sorted(hashed) == ["c.txt", "d.txt"]


def test_plan_items_target_the_review_folder(make, tmp_path):
    root = build(make)
    found = dedupe.groups([p for p in root.rglob("*") if p.is_file()], [])
    items = dedupe.plan_items(found, tmp_path / "Review")
    assert all(i.action == "move" and i.dest.startswith(str(tmp_path / "Review")) for i in items)
    assert all(i.reason.startswith("duplicate of ") for i in items)


def test_purge_deletes_only_verified_twins(make):
    root = make({
        "Review/dup.txt": b"same", "Keep/orig.txt": b"same",
        "Review/lonely.txt": b"no twin anywhere",
        "Review/inside-only.txt": b"twin is in review", "Review/sub/inside-only-2.txt": b"twin is in review",
        "Review/changed.txt": b"version one", "Keep/changed.txt": b"version two!",
        "Review/zero.txt": b"", "Keep/zero.txt": b"",
    })
    search = [p for p in root.rglob("*") if p.is_file()]
    deleted, kept = dedupe.purge(root / "Review", search)
    assert [p.name for p in deleted] == ["dup.txt"]
    assert sorted(p.name for p in kept) == ["changed.txt", "inside-only-2.txt", "inside-only.txt", "lonely.txt",
                                            "zero.txt"]
    assert (root / "Keep/orig.txt").exists() and not (root / "Review/dup.txt").exists()
