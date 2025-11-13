from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from site2docs import rendering
from site2docs.builder import ClusterValidationError, Site2DocsBuilder, build_documents
from site2docs.config import BuildConfig, OutputConfig, QualityConfig
from site2docs.extraction import ExtractedPage
from site2docs.rendering import RenderedPage
from site2docs.graphing import Cluster


def test_build_documents_writes_manifest_and_logs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(rendering, "async_playwright", None)
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    html_path = input_dir / "page.html"
    html_path.write_text(
        """
        <html>
          <head><title>テストページ</title></head>
          <body>
            <h1>見出し</h1>
            <p>概要の一文です。</p>
            <a href="./detail.html">詳細</a>
          </body>
        </html>
        """,
        encoding="utf-8",
    )

    captured_at = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    os.utime(html_path, (captured_at.timestamp(), captured_at.timestamp()))

    output_dir = tmp_path / "output"
    config = BuildConfig(
        input_dir=input_dir,
        output=OutputConfig(output_dir),
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    result = build_documents(config)

    assert len(result.pages) == 1
    assert len(result.clusters) == 1
    assert result.pages[0].captured_at == captured_at
    assert result.render_fallback_pages == 1
    assert result.render_fallback_reasons == ("playwright_unavailable",)

    doc_path = output_dir / "docs" / f"{result.clusters[0].slug}.md"
    manifest_path = output_dir / "manifest.json"
    log_path = output_dir / "logs" / "build_summary.json"
    quality_report_path = output_dir / "logs" / "hallucination_report.json"

    assert doc_path.exists()
    assert manifest_path.exists()
    assert log_path.exists()
    assert quality_report_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["pages"][0]["created_at"].startswith("2024-01-02T03:04:05")

    summary_lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert summary_lines, "ログにイベントが記録されていません"
    last_event = json.loads(summary_lines[-1])
    assert last_event["documents"]
    assert last_event["pages"] == 1
    assert last_event["clusters"] == 1
    assert last_event["fallback_pages"] == 1
    assert last_event["fallback_reasons"] == ["playwright_unavailable"]
    assert len(summary_lines) >= 2, "少なくとも2件以上のイベントが記録される想定です"

    markdown = doc_path.read_text(encoding="utf-8")
    assert "## 概要" in markdown
    assert "見出し" in markdown
    assert "ファイルパス" in markdown

    report = json.loads(quality_report_path.read_text(encoding="utf-8"))
    assert report["inspected_pages"] == 1
    assert result.quality_report_path == quality_report_path
    assert result.quality_findings == len(report["findings"])


def test_discover_html_files_supports_multiple_extensions(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    html_upper = input_dir / "index.HTML"
    html_upper.write_text("<html></html>", encoding="utf-8")
    html_short = input_dir / "detail.htm"
    html_short.write_text("<html></html>", encoding="utf-8")
    ignored = input_dir / "readme.txt"
    ignored.write_text("text", encoding="utf-8")

    builder = Site2DocsBuilder(
        BuildConfig(
            input_dir=input_dir,
            output=OutputConfig(tmp_path / "output"),
        )
    )

    discovered = list(builder._discover_html_files(input_dir))

    assert html_upper in discovered
    assert html_short in discovered
    assert ignored not in discovered


def test_write_outputs_detects_invalid_cluster(tmp_path: Path) -> None:
    builder = Site2DocsBuilder(
        BuildConfig(
            input_dir=tmp_path / "input",
            output=OutputConfig(tmp_path / "output"),
        )
    )
    page_path = tmp_path / "input" / "page.html"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text("<html></html>", encoding="utf-8")
    pages = [
        ExtractedPage(
            page_id="pg_001",
            url="https://example.com/",
            file_path=page_path,
            title="title",
            markdown="body",
            headings=[],
            links=[],
            captured_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
    ]
    clusters = [
        Cluster(
            cluster_id="cl_invalid",
            label="invalid",
            slug="invalid",
            page_ids=["pg_missing"],
        )
    ]

    with pytest.raises(ClusterValidationError) as exc:
        builder._write_outputs(pages, clusters)

    assert exc.value.missing_pages == {"cl_invalid": ("pg_missing",)}


def test_extract_rendered_pages_recovers_from_extraction_failure(tmp_path: Path, monkeypatch, caplog) -> None:
    caplog.set_level("INFO")
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    html_ok = input_dir / "ok.html"
    html_fail = input_dir / "fail.html"
    html_ok.write_text("<html><body>ok</body></html>", encoding="utf-8")
    html_fail.write_text("<html><body>ng</body></html>", encoding="utf-8")

    builder = Site2DocsBuilder(
        BuildConfig(
            input_dir=input_dir,
            output=OutputConfig(tmp_path / "output"),
        )
    )
    builder._prepare_logging_resources()

    rendered_pages = [
        RenderedPage(
            source_path=html_fail,
            final_html=html_fail.read_text(encoding="utf-8"),
            final_url="https://example.com/fail",
            render_mode="plain",
        ),
        RenderedPage(
            source_path=html_ok,
            final_html=html_ok.read_text(encoding="utf-8"),
            final_url="https://example.com/ok",
            render_mode="plain",
        ),
    ]

    def fake_extract(
        page_id: str,
        html: str,
        *,
        url: str,
        file_path: Path,
        captured_at: datetime,
    ) -> ExtractedPage:
        if page_id.endswith("001"):
            raise RuntimeError("boom")
        return ExtractedPage(
            page_id=page_id,
            url=url,
            file_path=file_path,
            title="ok",
            markdown=html,
            headings=[],
            links=[],
            captured_at=captured_at,
        )

    monkeypatch.setattr(builder.extractor, "extract", fake_extract)

    result = asyncio.run(builder._extract_rendered_pages(rendered_pages, total_html=2))

    assert len(result) == 1
    assert result[0].page_id.endswith("002")
    assert any("抽出に失敗" in record.message for record in caplog.records)

    summary_lines = [
        line for line in builder._summary_path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    events = [json.loads(line) for line in summary_lines]
    assert any(event.get("failed") == 1 for event in events)


def test_quality_checks_can_be_disabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(rendering, "async_playwright", None)
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    html_path = input_dir / "page.html"
    html_path.write_text("<html><body>sample</body></html>", encoding="utf-8")

    config = BuildConfig(
        input_dir=input_dir,
        output=OutputConfig(tmp_path / "output"),
        quality=QualityConfig(enable_hallucination_checks=False),
    )

    result = build_documents(config)

    assert result.quality_report_path is None
    assert result.quality_findings == 0
