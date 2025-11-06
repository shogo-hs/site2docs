from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from site2docs.graphing import GraphConfig, SiteGraph
from site2docs.extraction import ExtractedPage


def test_cluster_slug_uniqueness(tmp_path: Path) -> None:
    pages = []
    for idx, directory in enumerate(("group1", "group2"), start=1):
        dir_path = tmp_path / directory
        dir_path.mkdir()
        for inner in range(2):
            page_id = f"pg_{idx}{inner}"
            file_path = dir_path / f"page{inner}.html"
            file_path.write_text("<html></html>", encoding="utf-8")
            pages.append(
                ExtractedPage(
                    page_id=page_id,
                    url=f"https://example.com/{directory}/{inner}",
                    file_path=file_path,
                    title="",
                    markdown="共有 ラベル コンテンツ",
                    headings=[],
                    links=[],
                    captured_at=datetime.now(timezone.utc),
                )
            )

    graph = SiteGraph(GraphConfig())

    def constant_label(_: list[str]) -> str:
        return "共有ラベル"

    graph._infer_label = constant_label  # type: ignore[assignment]

    clusters = graph.cluster(pages)

    slugs = {cluster.slug for cluster in clusters}
    cluster_ids = {cluster.cluster_id for cluster in clusters}

    assert len(clusters) == 2
    assert len(slugs) == 2
    assert len(cluster_ids) == 2
