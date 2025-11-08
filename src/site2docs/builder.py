"""アーカイブ済みサイトをドキュメントへ変換するための中核オーケストレーター。"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .config import BuildConfig
from .document import build_markdown, write_markdown
from .extraction import ContentExtractor, ExtractedPage
from .graphing import Cluster, SiteGraph
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
        self._logger = logging.getLogger(self.__class__.__module__ + "." + self.__class__.__name__)
        self._summary_base = {
            "input_dir": str(config.input_dir),
            "output_dir": str(config.output.root),
            "created_at": config.created_at.isoformat(),
        }
        self._summary_path = config.output.logs_dir / "build_summary.json"

    async def build(self) -> BuildResult:
        html_paths = sorted(self._discover_html_files(self.config.input_dir))
        total_html = len(html_paths)
        self._prepare_logging_resources()
        self._update_summary("discovered", total_html=total_html)
        self._logger.info("HTML ファイルを %d 件検出しました。", total_html)

        rendered_pages = await render_paths(html_paths, self.config.render, progress=self._report_render_progress)
        self._update_summary("rendered", total_html=total_html, rendered=len(rendered_pages))
        self._logger.info("レンダリングが完了しました (%d 件)。", len(rendered_pages))

        pages: list[ExtractedPage] = []
        for index, rendered in enumerate(rendered_pages, start=1):
            page_id = f"pg_{index:03d}"
            captured_at = self._infer_captured_at(rendered.source_path)
            pages.append(
                self.extractor.extract(
                    page_id,
                    rendered.final_html,
                    url=rendered.final_url,
                    file_path=rendered.source_path,
                    captured_at=captured_at,
                )
            )
            self._logger.info("抽出中 (%d/%d): %s", index, len(rendered_pages), rendered.source_path.name)
            self._update_summary(
                "extracting",
                total_html=total_html,
                rendered=len(rendered_pages),
                extracted=index,
                last_file=str(rendered.source_path),
            )

        clusters = self.graph.cluster(pages)
        self._logger.info("クラスタリング完了: %d 件", len(clusters))
        self._update_summary(
            "clustering",
            total_html=total_html,
            rendered=len(rendered_pages),
            extracted=len(pages),
            clusters=len(clusters),
        )

        artifacts = self._write_outputs(pages, clusters)
        self._update_summary(
            "completed",
            pages=len(pages),
            clusters=len(clusters),
            documents=len(artifacts["documents"]),
            last_document=artifacts.get("last_document"),
            manifest=str(artifacts["manifest"]),
        )
        return BuildResult(pages=pages, clusters=clusters)

    def _discover_html_files(self, directory: Path) -> Iterable[Path]:
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in {".html", ".htm"}:
                yield path

    def _write_outputs(self, pages: list[ExtractedPage], clusters) -> dict[str, Any]:
        output = self.config.output
        output.root.mkdir(parents=True, exist_ok=True)
        output.docs_dir.mkdir(parents=True, exist_ok=True)
        output.logs_dir.mkdir(parents=True, exist_ok=True)

        generated_docs: list[str] = []
        last_document: str | None = None
        for index, cluster in enumerate(clusters, start=1):
            markdown = build_markdown(cluster, pages, self.config.created_at)
            doc_path = output.docs_dir / f"{cluster.slug or cluster.cluster_id}.md"
            write_markdown(doc_path, markdown)
            generated_docs.append(str(doc_path))
            last_document = str(doc_path)
            self._logger.info("Markdown を出力しました (%d/%d): %s", index, len(clusters), doc_path.name)
            self._update_summary(
                "writing",
                pages=len(pages),
                clusters=len(clusters),
                documents_count=len(generated_docs),
                last_document=str(doc_path),
            )

        manifest = build_manifest(pages, clusters, self.config.created_at)
        manifest_path = output.root / "manifest.json"
        write_manifest(manifest_path, manifest)
        self._logger.info("manifest.json を出力しました。")
        return {"documents": generated_docs, "manifest": manifest_path, "last_document": last_document}

    def _infer_captured_at(self, path: Path) -> datetime:
        try:
            timestamp = path.stat().st_mtime
        except OSError:
            return self.config.created_at
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)

    def _prepare_logging_resources(self) -> None:
        self.config.output.root.mkdir(parents=True, exist_ok=True)
        self.config.output.logs_dir.mkdir(parents=True, exist_ok=True)
        self._summary_path.write_text("", encoding="utf-8")

    def _report_render_progress(self, current: int, total: int, path: Path) -> None:
        self._logger.info("レンダリング中 (%d/%d): %s", current, total, path.name)
        self._update_summary(
            "rendering",
            total_html=total,
            rendered=current,
            last_file=str(path),
        )

    def _update_summary(self, stage: str, **extra: Any) -> None:
        payload = dict(self._summary_base)
        payload.update(extra)
        payload["stage"] = stage
        self._summary_path.parent.mkdir(parents=True, exist_ok=True)
        with self._summary_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False))
            stream.write("\n")


def build_documents(config: BuildConfig) -> BuildResult:
    builder = Site2DocsBuilder(config)
    return asyncio.run(builder.build())
