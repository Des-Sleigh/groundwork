"""Persistence + fetch cache (offline, temp DB)."""


from core import store


def _result():
    return {
        "answer": "An answer.",
        "n_tasks": 2, "n_accepted": 2, "n_revised": 1,
        "cost": {"total_usd": 0.012},
        "worker_results": [
            {"grounding": {"verified": 3, "total": 4}},
            {"grounding": {"verified": 1, "total": 2}},
        ],
        "trace": [{"kind": "thought", "label": "x"}],
    }


def test_run_roundtrip(tmp_path):
    db = str(tmp_path / "g.db")
    rid = store.save_run(db, "What is X?", "mock", _result())
    assert rid >= 1

    listed = store.list_runs(db)
    assert len(listed) == 1
    row = listed[0]
    assert row["question"] == "What is X?"
    assert row["grounding_verified"] == 4 and row["grounding_total"] == 6  # summed across workers
    assert row["cost_usd"] == 0.012

    full = store.get_run(db, rid)
    assert full["result"]["answer"] == "An answer."
    assert full["trace"][0]["label"] == "x"


def test_get_missing_run(tmp_path):
    assert store.get_run(str(tmp_path / "g.db"), 999) is None


def test_runs_ordered_desc(tmp_path):
    db = str(tmp_path / "g.db")
    store.save_run(db, "first", "mock", _result())
    store.save_run(db, "second", "mock", _result())
    listed = store.list_runs(db)
    assert [r["question"] for r in listed] == ["second", "first"]


def test_fetch_cache_hit_and_ttl(tmp_path):
    db = str(tmp_path / "g.db")
    store.cache_put(db, "https://example.com", "Example", "cached body")
    hit = store.cache_get(db, "https://example.com")
    assert hit and hit.text == "cached body" and hit.title == "Example"

    # Expired by TTL -> miss.
    assert store.cache_get(db, "https://example.com", ttl=-1) is None
    # Unknown URL -> miss.
    assert store.cache_get(db, "https://nope.com") is None


def test_cache_upsert(tmp_path):
    db = str(tmp_path / "g.db")
    store.cache_put(db, "https://example.com", "Old", "old")
    store.cache_put(db, "https://example.com", "New", "new")
    hit = store.cache_get(db, "https://example.com")
    assert hit.title == "New" and hit.text == "new"
