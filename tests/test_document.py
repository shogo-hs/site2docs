from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from site2docs.document import build_markdown
from site2docs.extraction import ExtractedPage
from site2docs.graphing import Cluster


def test_build_markdown_falls_back_to_cluster_id_for_slug(tmp_path: Path) -> None:
    page_path = tmp_path / "index.html"
    page_path.write_text("<html></html>", encoding="utf-8")
    page = ExtractedPage(
        page_id="pg_001",
        url="https://example.com/",
        file_path=page_path,
        title="タイトル",
        markdown="本文",
        headings=[],
        links=[],
        captured_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    cluster = Cluster(
        cluster_id="cl_001",
        label="ラベル",
        slug="",
        page_ids=["pg_001"],
    )

    markdown = build_markdown(cluster, [page], datetime(2024, 1, 1, tzinfo=timezone.utc))

    assert "doc_id: doc_cl_001" in markdown
    assert "cluster_slug: cl_001" in markdown
