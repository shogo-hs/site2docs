from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

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


def test_cluster_by_url_pattern(tmp_path: Path) -> None:
    base_dir = tmp_path / "pages"
    base_dir.mkdir()

    def create_page(page_id: str, url: str) -> ExtractedPage:
        parsed = urlparse(url)
        segments = [segment for segment in parsed.path.split("/") if segment]
        directory = base_dir
        if segments:
            directory = base_dir / Path(*segments[:-1]) if len(segments) > 1 else base_dir
        directory.mkdir(parents=True, exist_ok=True)
        file_path = directory / f"{page_id}.html"
        file_path.write_text("<html></html>", encoding="utf-8")
        return ExtractedPage(
            page_id=page_id,
            url=url,
            file_path=file_path,
            title="",
            markdown="テスト コンテンツ",
            headings=[],
            links=[],
            captured_at=datetime.now(timezone.utc),
        )

    pages = [
        create_page("pg_docs1", "https://example.com/docs/guide/2024/intro"),
        create_page("pg_docs2", "https://example.com/docs/guide/2023/overview"),
        create_page("pg_docs3", "https://example.com/docs/other/alpha"),
        create_page("pg_blog", "https://blog.example.com/posts/001"),
    ]

    graph = SiteGraph(GraphConfig(min_cluster_size=2, url_pattern_depth=3))

    clusters = graph.cluster(pages)

    cluster_sets = [set(cluster.page_ids) for cluster in clusters]

    assert {"pg_docs1", "pg_docs2"} in cluster_sets
    aggregated = sorted(page_id for cluster in clusters for page_id in cluster.page_ids)
    assert aggregated == sorted(page.page_id for page in pages)
