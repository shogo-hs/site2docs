"""アーカイブ済みサイトをドキュメントへ変換するための中核オーケストレーター。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .graphing import Cluster

from .config import BuildConfig
from .document import build_markdown, write_markdown
from .extraction import ContentExtractor, ExtractedPage
from .graphing import SiteGraph
from .manifest import build_manifest, write_manifest
from .rendering import render_paths


@dataclass(slots=True)
class BuildResult:
    pages: list[ExtractedPage]
    clusters: list[Cluster]


class Site2DocsBuilder:
    """レンダリング・抽出・出力を統括する高レベルパイプライン。"""

    def __init__(self, config: BuildConfig) -> None:
        self.config = config
        self.extractor = ContentExtractor(config.extract)
        self.graph = SiteGraph(config.graph)

    async def build(self) -> BuildResult:
        html_paths = sorted(self._discover_html_files(self.config.input_dir))
        rendered_pages = await render_paths(html_paths, self.config.render)

        pages: list[ExtractedPage] = []
        for index, rendered in enumerate(rendered_pages, start=1):
            page_id = f"pg_{index:03d}"
            pages.append(
                self.extractor.extract(
                    page_id,
                    rendered.final_html,
                    url=rendered.final_url,
                    file_path=rendered.source_path,
                    captured_at=self.config.created_at,
                )
            )

        clusters = self.graph.cluster(pages)
        self._write_outputs(pages, clusters)
        return BuildResult(pages=pages, clusters=clusters)

    def _discover_html_files(self, directory: Path) -> Iterable[Path]:
        for path in directory.rglob("*.html"):
            if path.is_file():
                yield path

    def _write_outputs(self, pages: list[ExtractedPage], clusters) -> None:
        output = self.config.output
        output.root.mkdir(parents=True, exist_ok=True)
        output.docs_dir.mkdir(parents=True, exist_ok=True)
        output.logs_dir.mkdir(parents=True, exist_ok=True)

        for cluster in clusters:
            markdown = build_markdown(cluster, pages, self.config.created_at)
            doc_path = output.docs_dir / f"{cluster.slug or cluster.cluster_id}.md"
            write_markdown(doc_path, markdown)

        manifest = build_manifest(pages, clusters, self.config.created_at)
        write_manifest(output.root / "manifest.json", manifest)


def build_documents(config: BuildConfig) -> BuildResult:
    builder = Site2DocsBuilder(config)
    return asyncio.run(builder.build())
