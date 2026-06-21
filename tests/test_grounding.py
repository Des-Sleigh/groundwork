"""Grounding verification: supported claims pass, fabricated claims are flagged."""

from core.types import Source
from mcp_server import tools
from research_agent.grounding import verify_answer

SOURCES = [
    Source(url="file://s1", title="Forecasting",
           text="Mid-market logistics firms use machine learning for demand forecasting. "
                "Forecast accuracy is measured with weighted MAPE."),
    Source(url="file://s2", title="ROI",
           text="Reported inventory reductions range from ten to twenty percent."),
]


def test_supported_claim_grounds():
    r = tools.check_grounding("Logistics firms use machine learning for demand forecasting.", SOURCES)
    assert r.supported
    assert r.best_source_url == "file://s1"


def test_fabricated_claim_is_flagged():
    r = tools.check_grounding("The moon is made of green cheese and orbits Jupiter.", SOURCES)
    assert not r.supported


def test_verify_answer_report_counts():
    answer = (
        "Mid-market logistics firms use machine learning for demand forecasting. "
        "Reported inventory reductions range from ten to twenty percent. "
        "Unicorns manage every warehouse using telepathy."
    )
    report = verify_answer(answer, SOURCES)
    assert report.total == 3
    assert report.verified >= 2          # the two real claims ground
    assert len(report.flagged) >= 1      # the fabricated one is flagged
    assert "verified" in report.summary()


def test_extract_claims_skips_questions_and_fragments():
    claims = tools.extract_claims("Short. Is this a question? "
                                  "This is a long enough declarative sentence to count as a claim.")
    assert any("declarative sentence" in c.text for c in claims)
    assert all(not c.text.endswith("?") for c in claims)
