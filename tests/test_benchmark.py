"""Benchmark guards (offline, no key): grounding must beat naive RAG."""

from benchmark.run import _score, lexical_decider, naive_decider


def test_naive_ships_all_hallucinations():
    m = _score(naive_decider)
    assert m["hallucination_passthrough"] == 1.0   # no verification -> ships everything
    assert m["valid_retention"] == 1.0


def test_grounding_beats_naive():
    naive = _score(naive_decider)
    lexical = _score(lexical_decider)
    # Far fewer hallucinations shipped...
    assert lexical["hallucination_passthrough"] < naive["hallucination_passthrough"]
    assert lexical["hallucination_passthrough"] <= 0.4
    # ...without dropping valid claims.
    assert lexical["valid_retention"] >= 0.9
