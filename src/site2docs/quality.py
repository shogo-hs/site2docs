"""品質検証とハルシネーション抑制のためのユーティリティ。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Mapping, Sequence

from .config import QualityConfig
from .document import build_summary_snippets
from .extraction import ExtractedPage
from .graphing import Cluster


@dataclass(slots=True)
class HallucinationFinding:
    """検知された問題 1 件を表すデータモデル。"""

    cluster_id: str
    page_id: str | None
    kind: str
    message: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "cluster_id": self.cluster_id,
            "page_id": self.page_id,
            "kind": self.kind,
            "message": self.message,
        }


@dataclass(slots=True)
class HallucinationReport:
    """ハルシネーションチェックの結果。"""

    findings: list[HallucinationFinding]
    inspected_clusters: int
    inspected_pages: int

    def to_dict(self) -> dict[str, object]:
        return {
            "inspected_clusters": self.inspected_clusters,
            "inspected_pages": self.inspected_pages,
            "findings": [finding.to_dict() for finding in self.findings],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class HallucinationGuard:
    """抽出結果が出典から乖離していないかを検査するノード。"""

    def __init__(self, config: QualityConfig) -> None:
        self._config = config

    def inspect(
        self,
        clusters: Sequence[Cluster],
        resolved_pages: Mapping[str, Sequence[ExtractedPage]],
    ) -> HallucinationReport:
        findings: list[HallucinationFinding] = []
        inspected_pages = 0
        for cluster in clusters:
            pages = list(resolved_pages.get(cluster.cluster_id, ()))
            inspected_pages += len(pages)
            if not pages:
                findings.append(
                    HallucinationFinding(
                        cluster_id=cluster.cluster_id,
                        page_id=None,
                        kind="empty_cluster",
                        message="クラスタに紐づくページが存在しません。",
                    )
                )
                continue
            findings.extend(self._evaluate_page_quality(cluster, pages))
            findings.extend(self._evaluate_label_grounding(cluster, pages))
            findings.extend(self._evaluate_summary_grounding(cluster, pages))
        return HallucinationReport(
            findings=findings,
            inspected_clusters=len(clusters),
            inspected_pages=inspected_pages,
        )

    # Internal helpers -------------------------------------------------

    def _evaluate_page_quality(
        self, cluster: Cluster, pages: Sequence[ExtractedPage]
    ) -> list[HallucinationFinding]:
        findings: list[HallucinationFinding] = []
        min_chars = max(0, self._config.min_page_characters)
        for page in pages:
            normalized = page.markdown.strip()
            if len(normalized) < min_chars:
                findings.append(
                    HallucinationFinding(
                        cluster_id=cluster.cluster_id,
                        page_id=page.page_id,
                        kind="insufficient_content",
                        message=(
                            f"ページ本文が {len(normalized)} 文字しかないため、"
                            f"抽出結果の信頼性が十分とは言えません (閾値: {min_chars})。"
                        ),
                    )
                )
            if self._config.require_source_url and not page.url:
                findings.append(
                    HallucinationFinding(
                        cluster_id=cluster.cluster_id,
                        page_id=page.page_id,
                        kind="missing_source_url",
                        message="URL が空のため、回答根拠を追跡できません。",
                    )
                )
        return findings

    def _evaluate_label_grounding(
        self, cluster: Cluster, pages: Sequence[ExtractedPage]
    ) -> list[HallucinationFinding]:
        if not cluster.label:
            return []
        combined_text = "\n".join(page.markdown.lower() for page in pages if page.markdown)
        if not combined_text.strip():
            return []
        min_token_length = max(1, self._config.label_min_token_length)
        tokens = [
            token
            for token in re.split(r"[\s\-/|,_]+", cluster.label.lower())
            if len(token) >= min_token_length
        ]
        findings: list[HallucinationFinding] = []
        for token in tokens:
            if token and token not in combined_text:
                findings.append(
                    HallucinationFinding(
                        cluster_id=cluster.cluster_id,
                        page_id=None,
                        kind="label_not_in_content",
                        message=(
                            f"クラスタラベルの語 '{token}' が、いずれのページ本文にも"
                            " 含まれていません。命名とコンテンツのズレが疑われます。"
                        ),
                    )
                )
        return findings

    def _evaluate_summary_grounding(
        self, cluster: Cluster, pages: Sequence[ExtractedPage]
    ) -> list[HallucinationFinding]:
        snippets = build_summary_snippets(
            pages, limit=max(1, self._config.summary_snippet_limit)
        )
        if not snippets:
            return []
        lookup = {page.page_id: page for page in pages}
        findings: list[HallucinationFinding] = []
        for page_id, snippet in snippets:
            page = lookup.get(page_id)
            if page is None or not snippet:
                continue
            if snippet not in page.markdown:
                findings.append(
                    HallucinationFinding(
                        cluster_id=cluster.cluster_id,
                        page_id=page_id,
                        kind="summary_not_in_source",
                        message="サマリーの文が元ページ本文に見つかりません。",
                    )
                )
        if len(snippets) < min(len(pages), self._config.summary_snippet_limit):
            findings.append(
                HallucinationFinding(
                    cluster_id=cluster.cluster_id,
                    page_id=None,
                    kind="insufficient_summary_coverage",
                    message="想定より少ないサマリーしか生成できませんでした。",
                )
            )
        return findings
