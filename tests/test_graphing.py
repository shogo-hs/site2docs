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


def test_cluster_label_uses_url_prefix_when_text_sparse(tmp_path: Path) -> None:
    pages: list[ExtractedPage] = []
    base_dir = tmp_path / "cluster"
    base_dir.mkdir()
    for idx in range(2):
        file_path = base_dir / f"page{idx}.html"
        file_path.write_text("<html></html>", encoding="utf-8")
        pages.append(
            ExtractedPage(
                page_id=f"pg_label_{idx}",
                url=f"https://example.com/docs/tutorial/{idx}",
                file_path=file_path,
                title="",
                markdown="",
                headings=[],
                links=[],
                captured_at=datetime.now(timezone.utc),
            )
        )

    graph = SiteGraph(GraphConfig(min_cluster_size=1, url_pattern_depth=3))
    clusters = graph.cluster(pages)

    assert clusters, "クラスタが生成されていません"
    target = next(cluster for cluster in clusters if set(cluster.page_ids) == {"pg_label_0", "pg_label_1"})
    assert "example.com/docs/tutorial" in target.label


def test_directory_grouping_clusters_pages_without_url_overlap(tmp_path: Path) -> None:
    base_dir = tmp_path / "site_backup" / "example.com"
    (base_dir / "service" / "alpha").mkdir(parents=True)
    (base_dir / "service" / "beta").mkdir(parents=True)

    pages = []
    for idx, name in enumerate(("alpha", "beta"), start=1):
        file_path = base_dir / "service" / name / "index.html"
        file_path.write_text("<html></html>", encoding="utf-8")
        pages.append(
            ExtractedPage(
                page_id=f"pg_dir_{idx}",
                url=file_path.as_uri(),  # URL パターンが使えないケースを再現
                file_path=file_path,
                title="",
                markdown="",
                headings=[],
                links=[],
                captured_at=datetime.now(timezone.utc),
            )
        )

    graph = SiteGraph(GraphConfig(min_cluster_size=2, directory_cluster_depth=1))
    clusters = graph.cluster(pages)

    assert any(set(cluster.page_ids) == {"pg_dir_1", "pg_dir_2"} for cluster in clusters)


def test_singletons_are_merged_by_host(tmp_path: Path) -> None:
    base_dir = tmp_path / "site_backup" / "sample.com"
    for idx in range(3):
        path = base_dir / f"landing{idx}" / "index.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<html></html>", encoding="utf-8")
    pages = []
    for idx in range(3):
        file_path = base_dir / f"landing{idx}" / "index.html"
        pages.append(
            ExtractedPage(
                page_id=f"pg_single_{idx}",
                url=f"https://sample.com/landing{idx}/",
                file_path=file_path,
                title="",
                markdown="",
                headings=[],
                links=[],
                captured_at=datetime.now(timezone.utc),
            )
        )

    graph = SiteGraph(GraphConfig(min_cluster_size=2))
    clusters = graph.cluster(pages)

    assert any(len(cluster.page_ids) == 3 for cluster in clusters)
