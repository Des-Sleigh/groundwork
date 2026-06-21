"""Eval regression guards (offline, no key).

Locks in the reproducible grounding/injection numbers so a change that quietly
degrades them fails CI.
"""

from evals.run import eval_grounding_lexical, eval_injection


def test_lexical_grounding_quality():
    m = eval_grounding_lexical()
    assert m["n"] == 12
    assert m["accuracy"] >= 0.8
    assert m["recall"] >= 0.8


def test_injection_detection_quality():
    m = eval_injection()
    assert m["n"] == 8
    assert m["accuracy"] >= 0.85
    assert m["precision"] >= 0.85
