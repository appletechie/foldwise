from foldwise.cache import Cache


def test_cache_reuses_until_file_changes(make, tmp_path, monkeypatch):
    root = make({"a.txt": "first"})
    calls = []
    import foldwise.cache as cache_mod
    real = cache_mod.extract.read
    monkeypatch.setattr(cache_mod.extract, "read", lambda p, timeout=30.0: calls.append(p) or real(p, timeout))
    c = Cache(tmp_path / "cache.jsonl")
    assert c.read(root / "a.txt").text == "first"
    assert c.read(root / "a.txt").text == "first"
    assert len(calls) == 1
    (root / "a.txt").write_text("second, longer")
    assert c.read(root / "a.txt").text == "second, longer"
    c.close()
    c2 = Cache(tmp_path / "cache.jsonl")
    assert c2.read(root / "a.txt").text == "second, longer"
    assert len(calls) == 2
    c2.close()
