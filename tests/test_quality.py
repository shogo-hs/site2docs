from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from site2docs.config import QualityConfig
from site2docs.extraction import ExtractedPage
from site2docs.graphing import Cluster
from site2docs.quality import HallucinationGuard


def _page(page_id: str, markdown: str, url: str = "https://example.com/") -> ExtractedPage:
    return ExtractedPage(
        page_id=page_id,
        url=url,
        file_path=Path(f"/tmp/{page_id}.html"),
        title="title",
        markdown=markdown,
        headings=[],
        links=[],
        captured_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def test_guard_detects_short_content() -> None:
    guard = HallucinationGuard(QualityConfig(min_page_characters=50))
    cluster = Cluster(cluster_id="cl_test", label="Alpha", slug="alpha", page_ids=["pg_001"])
    pages = [_page("pg_001", "short text")]

    report = guard.inspect([cluster], {cluster.cluster_id: pages})

    assert any(f.kind == "insufficient_content" for f in report.findings)


def test_guard_flags_label_mismatch() -> None:
    guard = HallucinationGuard(QualityConfig(label_min_token_length=4))
    cluster = Cluster(cluster_id="cl_test", label="Secret Feature", slug="secret", page_ids=["pg_001"])
    pages = [_page("pg_001", "これは公開済みの概要です。")]

    report = guard.inspect([cluster], {cluster.cluster_id: pages})

    assert any(f.kind == "label_not_in_content" for f in report.findings)
