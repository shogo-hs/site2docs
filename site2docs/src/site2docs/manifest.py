"""マニフェスト生成ユーティリティ。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

from .extraction import ExtractedPage
from .graphing import Cluster

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


@dataclass(slots=True)
class PageEntry:
    page_id: str
    url: str
    file_path: str
    title: str
    cluster_id: str
    created_at: str


@dataclass(slots=True)
class ClusterEntry:
    cluster_id: str
    label: str
    slug: str
    page_ids: list[str]


@dataclass(slots=True)
class Manifest:
    pages: list[PageEntry]
    clusters: list[ClusterEntry]

    def to_json(self) -> str:
        return json.dumps(
            {
                "pages": [asdict(page) for page in self.pages],
                "clusters": [asdict(cluster) for cluster in self.clusters],
            },
            ensure_ascii=False,
            indent=2,
        )


def build_manifest(pages: Sequence[ExtractedPage], clusters: Sequence[Cluster], created_at: datetime) -> Manifest:
    page_entries: list[PageEntry] = []
    cluster_lookup = {cluster.cluster_id: cluster for cluster in clusters}
    for page in pages:
        cluster_id = next((cid for cid, cluster in cluster_lookup.items() if page.page_id in cluster.page_ids), "")
        page_entries.append(
            PageEntry(
                page_id=page.page_id,
                url=page.url,
                file_path=str(page.file_path),
                title=page.title,
                cluster_id=cluster_id,
                created_at=page.captured_at.strftime(ISO_FORMAT),
            )
        )
    cluster_entries = [
        ClusterEntry(
            cluster_id=cluster.cluster_id,
            label=cluster.label,
            slug=cluster.slug,
            page_ids=list(cluster.page_ids),
        )
        for cluster in clusters
    ]
    return Manifest(pages=page_entries, clusters=cluster_entries)


def write_manifest(path: Path, manifest: Manifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.to_json(), encoding="utf-8")
