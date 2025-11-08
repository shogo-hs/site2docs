"""アーカイブ済みサイトをドキュメントへ変換するための中核オーケストレーター。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .config import BuildConfig
from .document import build_markdown, write_markdown
from .extraction import ContentExtractor, ExtractedPage
from .graphing import Cluster, SiteGraph
from .manifest import build_manifest, write_manifest
from .rendering import RenderedPage, render_paths


@dataclass(slots=True)
class BuildResult:
    pages: list[ExtractedPage]
    clusters: list[Cluster]
    render_fallback_pages: int
    render_fallback_reasons: tuple[str, ...]


class ClusterValidationError(RuntimeError):
    """クラスタと抽出結果の整合性が崩れた際に送出される例外。"""

    def __init__(self, *, missing_pages: Mapping[str, Sequence[str]]) -> None:
        self.missing_pages: dict[str, tuple[str, ...]] = {
            cluster_id: tuple(page_ids)
            for cluster_id, page_ids in missing_pages.items()
        }
        details = ", ".join(
            f"{cluster_id}: {', '.join(page_ids)}"
            for cluster_id, page_ids in self.missing_pages.items()
        )
        message = "クラスタに存在しないページ ID が参照されています: " + details
        super().__init__(message)


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

        rendered_pages = await render_paths(
            html_paths, self.config.render, progress=self._report_render_progress
        )
        fallback_pages = [page for page in rendered_pages if page.render_mode != "playwright"]
        fallback_reasons = sorted(
            {
                reason if reason else "unknown"
                for reason in (page.fallback_reason for page in fallback_pages)
            }
        )
        self._update_summary(
            "rendered",
            total_html=total_html,
            rendered=len(rendered_pages),
            fallback_pages=len(fallback_pages),
            fallback_reasons=fallback_reasons,
        )
        if fallback_pages:
            reason_text = ", ".join(fallback_reasons) if fallback_reasons else "不明"
            self._logger.warning(
                "Playwright レンダリングを利用できなかったページが %d 件あります (理由: %s)",
                len(fallback_pages),
                reason_text,
            )
        self._logger.info("レンダリングが完了しました (%d 件)。", len(rendered_pages))

        pages = await self._extract_rendered_pages(rendered_pages, total_html)

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
            fallback_pages=len(fallback_pages),
            fallback_reasons=fallback_reasons,
        )
        return BuildResult(
            pages=pages,
            clusters=clusters,
            render_fallback_pages=len(fallback_pages),
            render_fallback_reasons=tuple(fallback_reasons),
        )

    def _discover_html_files(self, directory: Path) -> Iterable[Path]:
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in {".html", ".htm"}:
                yield path

    async def _extract_rendered_pages(
        self, rendered_pages: Sequence[RenderedPage], total_html: int
    ) -> list[ExtractedPage]:
        total = len(rendered_pages)
        if total == 0:
            return []
        worker_count = self._determine_extract_workers(total)
        semaphore = asyncio.Semaphore(worker_count)
        progress_lock = asyncio.Lock()
        completed = 0
        successful = 0
        failed_count = 0
        failed_paths: list[Path] = []
        results: list[ExtractedPage | None] = [None] * total

        async def process(index: int, rendered: RenderedPage) -> None:
            nonlocal completed, successful, failed_count
            async with semaphore:
                captured_at = self._infer_captured_at(rendered.source_path)
                try:
                    page = await asyncio.to_thread(
                        self.extractor.extract,
                        f"pg_{index + 1:03d}",
                        rendered.final_html,
                        url=rendered.final_url,
                        file_path=rendered.source_path,
                        captured_at=captured_at,
                    )
                except Exception as exc:  # pragma: no cover - defensive path
                    async with progress_lock:
                        completed += 1
                        current = completed
                        failed_count += 1
                        extracted_now = successful
                    failed_paths.append(rendered.source_path)
                    self._logger.error(
                        "抽出に失敗しました (%d/%d): %s (%s)",
                        current,
                        total,
                        rendered.source_path.name,
                        exc,
                        exc_info=exc,
                    )
                    self._update_summary(
                        "extracting",
                        total_html=total_html,
                        rendered=total,
                        extracted=extracted_now,
                        failed=failed_count,
                        last_file=str(rendered.source_path),
                        last_error=str(exc),
                    )
                    return
            results[index] = page
            async with progress_lock:
                completed += 1
                current = completed
                successful += 1
                extracted_now = successful
            self._logger.info(
                "抽出中 (%d/%d): %s",
                current,
                total,
                rendered.source_path.name,
            )
            self._update_summary(
                "extracting",
                total_html=total_html,
                rendered=total,
                extracted=extracted_now,
                failed=failed_count,
                last_file=str(rendered.source_path),
            )

        await asyncio.gather(
            *(process(index, rendered) for index, rendered in enumerate(rendered_pages))
        )

        if failed_paths:
            samples = ", ".join(path.name for path in failed_paths[:3])
            self._logger.warning(
                "抽出に失敗したページが %d 件あります。サンプル: %s",
                failed_count,
                samples,
            )

        return [page for page in results if page is not None]

    def _determine_extract_workers(self, total: int) -> int:
        requested = self.config.extract.max_workers
        if requested is not None and requested > 0:
            return max(1, min(total, requested))
        cpu_total = os.cpu_count() or 2
        if cpu_total <= 1:
            baseline = 1
        elif cpu_total <= 4:
            baseline = cpu_total
        else:
            baseline = min(8, cpu_total // 2 + 2)
        return max(1, min(total, baseline))

    def _write_outputs(
        self,
        pages: Sequence[ExtractedPage],
        clusters: Sequence[Cluster],
    ) -> dict[str, Any]:
        output = self.config.output
        output.root.mkdir(parents=True, exist_ok=True)
        output.docs_dir.mkdir(parents=True, exist_ok=True)
        output.logs_dir.mkdir(parents=True, exist_ok=True)

        generated_docs: list[str] = []
        last_document: str | None = None
        resolved_pages = self._resolve_cluster_pages(pages, clusters)
        for index, cluster in enumerate(clusters, start=1):
            markdown = build_markdown(
                cluster,
                resolved_pages[cluster.cluster_id],
                self.config.created_at,
            )
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

    def _resolve_cluster_pages(
        self,
        pages: Sequence[ExtractedPage],
        clusters: Sequence[Cluster],
    ) -> dict[str, list[ExtractedPage]]:
        page_lookup = {page.page_id: page for page in pages}
        missing: dict[str, list[str]] = {}
        resolved: dict[str, list[ExtractedPage]] = {}
        for cluster in clusters:
            if not cluster.page_ids:
                missing.setdefault(cluster.cluster_id, []).append("<ページIDが定義されていません>")
                continue
            ordered: list[ExtractedPage] = []
            for page_id in cluster.page_ids:
                page = page_lookup.get(page_id)
                if page is None:
                    missing.setdefault(cluster.cluster_id, []).append(page_id)
                    continue
                ordered.append(page)
            if cluster.cluster_id in missing:
                continue
            resolved[cluster.cluster_id] = ordered
        if missing:
            raise ClusterValidationError(missing_pages=missing)
        return resolved

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
