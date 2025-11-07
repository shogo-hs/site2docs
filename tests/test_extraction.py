from __future__ import annotations

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
