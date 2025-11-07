"""HTML ページからコンテンツを抽出するユーティリティ群。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urldefrag

from .config import ExtractionConfig

try:  # pragma: no cover - optional dependency
    from readability import Document  # type: ignore
except Exception:  # pragma: no cover
    Document = None  # type: ignore[misc]

try:  # pragma: no cover - optional dependency
    import trafilatura  # type: ignore
except Exception:  # pragma: no cover
    trafilatura = None  # type: ignore[misc]

try:  # pragma: no cover - optional dependency
    from markdownify import markdownify as html_to_markdown  # type: ignore
except Exception:  # pragma: no cover
    html_to_markdown = None  # type: ignore[misc]

try:  # pragma: no cover - optional dependency
    from bs4 import BeautifulSoup  # type: ignore
except Exception:  # pragma: no cover
    BeautifulSoup = None  # type: ignore[misc]


@dataclass(slots=True)
class ExtractedPage:
    """HTML ページを正規化した表現。"""

    page_id: str
    url: str
    file_path: Path
    title: str
    markdown: str
    headings: list[str]
    links: list[str]
    captured_at: datetime


class _FallbackAnchorParser(HTMLParser):
    """BeautifulSoup が利用できない場合の簡易リンクパーサー。"""

    def __init__(self) -> None:
        super().__init__()
        self._links: list[str] = []

    @property
    def links(self) -> list[str]:
        return self._links

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = ""
        for name, value in attrs:
            if name.lower() == "href":
                href = (value or "").strip()
                break
        if not href or href.startswith(("javascript:", "mailto:", "tel:")):
            return
        self._links.append(href)


class ContentExtractor:
    """レンダリング済み HTML から記事相当のコンテンツを抽出します。"""

    def __init__(self, config: ExtractionConfig) -> None:
        self._config = config

    def extract(self, page_id: str, html: str, *, url: str, file_path: Path, captured_at: datetime) -> ExtractedPage:
        normalized_url = self._normalize_base_url(url, file_path)
        title, content_html = self._extract_readable(html)
        headings = self._extract_headings(content_html)
        links = self._extract_links(html, normalized_url)
        markdown = self._convert_to_markdown(content_html)
        return ExtractedPage(
            page_id=page_id,
            url=normalized_url,
            file_path=file_path,
            title=title,
            markdown=markdown,
            headings=headings,
            links=links,
            captured_at=captured_at,
        )

    # Internal helpers -------------------------------------------------

    def _extract_readable(self, html: str) -> tuple[str, str]:
        if self._config.readability and Document is not None:
            try:
                doc = Document(html)
                title = unescape(doc.short_title())
                summary_html = doc.summary(html_partial=True)
                if self._has_enough_content(summary_html):
                    return title, summary_html
            except Exception:
                pass
        if self._config.trafilatura and trafilatura is not None:
            try:
                extracted = trafilatura.extract(html, include_comments=False, include_tables=True, favor_recall=True)
                if extracted and self._has_enough_content(extracted):
                    return "", extracted
            except Exception:
                pass
        if not self._config.fallback_plain_text:
            raise RuntimeError(
                "読み取り可能な本文抽出に失敗しました。ExtractionConfig.fallback_plain_text を True に設定すると"
                " プレーンテキストへのフォールバックを有効化できます。"
            )
        if BeautifulSoup is None:
            return "", html
        soup = BeautifulSoup(html, "lxml") if BeautifulSoup is not None else None
        if soup is None:
            return "", html
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        main = soup.body or soup
        return title, str(main)

    def _extract_headings(self, content_html: str) -> list[str]:
        if BeautifulSoup is None or not self._config.preserve_headings:
            return []
        soup = BeautifulSoup(content_html, "lxml")
        headings: list[str] = []
        for level in ("h1", "h2", "h3"):
            for node in soup.find_all(level):
                text = node.get_text(strip=True)
                if text:
                    headings.append(text)
        return headings

    def _extract_links(self, html: str, base_url: str) -> list[str]:
        if BeautifulSoup is None:
            parser = _FallbackAnchorParser()
            parser.feed(html)
            candidates = parser.links
        else:
            soup = BeautifulSoup(html, "lxml")
            candidates = [(tag.get("href") or "").strip() for tag in soup.find_all("a")]
        links: set[str] = set()
        for href in candidates:
            if not href or href.startswith(("javascript:", "mailto:", "tel:")):
                continue
            resolved = self._resolve_link(href, base_url)
            if resolved:
                links.add(resolved)
        return sorted(links)

    def _convert_to_markdown(self, content_html: str) -> str:
        if html_to_markdown is not None:
            try:
                return html_to_markdown(content_html, strip="")
            except Exception:
                pass
        if BeautifulSoup is None:
            return content_html
        soup = BeautifulSoup(content_html, "lxml")
        return soup.get_text("\n")

    def _has_enough_content(self, content: str) -> bool:
        threshold = self._config.min_content_characters
        if threshold <= 0:
            return True
        return self._count_plain_text(content) >= threshold

    def _count_plain_text(self, content: str) -> int:
        if not content:
            return 0
        if BeautifulSoup is None:
            return len(content.strip())
        soup = BeautifulSoup(content, "lxml")
        text = soup.get_text(" ", strip=True)
        return len(text)

    def _normalize_base_url(self, url: str, file_path: Path) -> str:
        base = url or file_path.as_uri()
        normalized, _ = urldefrag(base)
        return normalized or file_path.as_uri()

    def _resolve_link(self, href: str, base_url: str) -> str:
        absolute = urljoin(base_url, href)
        normalized, _ = urldefrag(absolute)
        if not normalized or normalized == base_url:
            return ""
        return normalized


def extract_contents(
    pages: Iterable[ExtractedPage],
) -> list[ExtractedPage]:
    """後方互換性のために残している何もしないラッパー。"""

    return list(pages)
