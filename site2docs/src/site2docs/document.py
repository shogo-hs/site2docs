"""Markdown ドキュメント生成ユーティリティ。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

from .extraction import ExtractedPage
from .graphing import Cluster

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def build_markdown(cluster: Cluster, pages: Sequence[ExtractedPage], created_at: datetime) -> str:
    """クラスタに対応する Markdown ドキュメントを組み立てます。"""

    page_lookup = {page.page_id: page for page in pages}
    ordered_pages = [page_lookup[pid] for pid in cluster.page_ids]
    source_urls = [page.url for page in ordered_pages if page.url]
    frontmatter_lines = [
        "---",
        f"doc_id: doc_{cluster.slug}",
        f"cluster_label: {cluster.label}",
        f"cluster_slug: {cluster.slug}",
        "source_urls:",
    ]
    frontmatter_lines.extend([f"  - {url}" for url in source_urls])
    frontmatter_lines.append(f"created_at: {created_at.strftime(ISO_FORMAT)}")
    frontmatter_lines.append(
        "pages: [" + ", ".join(cluster.page_ids) + "]"
    )
    frontmatter_lines.append("---")

    body: list[str] = []
    body.append(f"# {cluster.label}\n")

    if any(page.headings for page in ordered_pages):
        body.append("## 目次")
        for page in ordered_pages:
            for heading in page.headings:
                body.append(f"- {heading}")
        body.append("")

    for page in ordered_pages:
        body.append(f"## {page.title or page.page_id}")
        body.append(
            f"> 出典: {page.url or page.file_path.as_posix()} （取得日時: {page.captured_at.strftime('%Y-%m-%d %Z')})"
        )
        body.append("")
        body.append(page.markdown.strip())
        body.append("")

    return "\n".join(frontmatter_lines + body)


def write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
