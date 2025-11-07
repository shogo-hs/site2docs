from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from site2docs import rendering
from site2docs.builder import build_documents
from site2docs.config import BuildConfig, OutputConfig


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

    doc_path = output_dir / "docs" / f"{result.clusters[0].slug}.md"
    manifest_path = output_dir / "manifest.json"
    log_path = output_dir / "logs" / "build_summary.json"

    assert doc_path.exists()
    assert manifest_path.exists()
    assert log_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["pages"][0]["created_at"].startswith("2024-01-02T03:04:05")

    summary_lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert summary_lines, "ログにイベントが記録されていません"
    last_event = json.loads(summary_lines[-1])
    assert last_event["documents"]
    assert last_event["pages"] == 1
    assert last_event["clusters"] == 1
    assert len(summary_lines) >= 2, "少なくとも2件以上のイベントが記録される想定です"

    markdown = doc_path.read_text(encoding="utf-8")
    assert "## 概要" in markdown
    assert "見出し" in markdown
    assert "ファイルパス" in markdown
