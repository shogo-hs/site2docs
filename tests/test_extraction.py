from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from site2docs.extraction import ContentExtractor, ExtractionConfig


def test_extract_normalizes_links(tmp_path: Path) -> None:
    html = """
    <html>
      <head><title>Example</title></head>
      <body>
        <a href="/docs/page.html#section">内部リンク</a>
        <a href="javascript:void(0)">無視するリンク</a>
        <a href="./relative/guide.html">相対リンク</a>
      </body>
    </html>
    """
    file_path = tmp_path / "index.html"
    file_path.write_text(html, encoding="utf-8")

    extractor = ContentExtractor(ExtractionConfig())
    page = extractor.extract(
        "pg_001",
        html,
        url="https://example.com/base/index.html#fragment",
        file_path=file_path,
        captured_at=datetime.now(timezone.utc),
    )

    assert page.url == "https://example.com/base/index.html"
    assert set(page.links) == {
        "https://example.com/docs/page.html",
        "https://example.com/base/relative/guide.html",
    }


def test_extract_raises_when_fallback_disabled(tmp_path: Path) -> None:
    html = "<html><body><p>example</p></body></html>"
    file_path = tmp_path / "index.html"
    file_path.write_text(html, encoding="utf-8")

    extractor = ContentExtractor(
        ExtractionConfig(
            readability=False,
            trafilatura=False,
            fallback_plain_text=False,
        )
    )

    with pytest.raises(RuntimeError):
        extractor.extract(
            "pg_001",
            html,
            url="",
            file_path=file_path,
            captured_at=datetime.now(timezone.utc),
        )


def test_extract_uses_semantic_body_when_readability_is_too_small(tmp_path: Path, monkeypatch) -> None:
    long_text = "重要な情報" * 200
    html = f"""
    <html>
      <head><title>サンプル</title></head>
      <body>
        <header>ナビゲーション</header>
        <div role="main">
          <section>
            <h2>本来拾いたい本文</h2>
            <p>{long_text}</p>
          </section>
        </div>
        <footer>フッター</footer>
      </body>
    </html>
    """
    file_path = tmp_path / "index.html"
    file_path.write_text(html, encoding="utf-8")

    from site2docs import extraction

    class DummyDocument:
        def __init__(self, _: str) -> None:
            pass

        def short_title(self) -> str:
            return "短い"

        def summary(self, html_partial: bool = True) -> str:  # noqa: ARG002
            return "<p>短い要約のみ</p>"

    monkeypatch.setattr(extraction, "Document", DummyDocument)
    monkeypatch.setattr(extraction, "trafilatura", None)

    extractor = ContentExtractor(ExtractionConfig())
    page = extractor.extract(
        "pg_001",
        html,
        url="https://example.com/page",
        file_path=file_path,
        captured_at=datetime.now(timezone.utc),
    )

    assert "本来拾いたい本文" in page.markdown
    assert "重要な情報" in page.markdown


def test_content_extractor_warns_when_optional_dependencies_missing(monkeypatch, caplog) -> None:
    from site2docs import extraction

    monkeypatch.setattr(extraction, "Document", None)
    monkeypatch.setattr(extraction, "trafilatura", None)
    monkeypatch.setattr(extraction, "BeautifulSoup", None)
    monkeypatch.setattr(extraction, "html_to_markdown", None)

    caplog.set_level(logging.WARNING)

    ContentExtractor(
        ExtractionConfig(
            readability=True,
            trafilatura=True,
            preserve_headings=True,
            semantic_body_fallback=True,
        )
    )

    messages = [record.message for record in caplog.records if record.levelno >= logging.WARNING]
    assert any("Readability" in message for message in messages)
    assert any("Trafilatura" in message for message in messages)
    assert any("BeautifulSoup" in message for message in messages)
    assert any("markdownify" in message for message in messages)
