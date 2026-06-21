"""Search/fetch backends: extraction + offline selection (no network)."""

from pathlib import Path

from mcp_server import backends

REDTEAM = Path(__file__).resolve().parent.parent / "redteam" / "injection_pages"


def test_extract_main_text_strips_markup():
    html = "<html><head><style>x{}</style></head><body><h1>Hi</h1><p>Body text here.</p></body></html>"
    text = backends.extract_main_text(html)
    assert "Body text here." in text
    assert "{" not in text and "<" not in text


def test_extract_title():
    assert backends.extract_title("<title>My Page</title>") == "My Page"
    assert backends.extract_title("<html></html>", fallback="fb") == "fb"


def test_local_backend_finds_corpus(tmp_path, monkeypatch):
    doc = tmp_path / "doc.md"
    doc.write_text("Mid-market logistics firms use AI for demand forecasting.")
    monkeypatch.setenv("GROUNDWORK_CORPUS", str(tmp_path))
    results = backends.LocalCorpusBackend().search("demand forecasting logistics", k=3)
    assert results and results[0]["url"].endswith("doc.md")


def test_get_search_backend_offline_is_local(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("GROUNDWORK_SEARCH_BACKEND", raising=False)
    assert backends.get_search_backend().name == "local"


def test_get_search_backend_picks_tavily_with_key(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.delenv("GROUNDWORK_SEARCH_BACKEND", raising=False)
    assert backends.get_search_backend().name == "tavily"
