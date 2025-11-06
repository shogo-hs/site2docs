"""サイトグラフを構築してクラスタリングするユーティリティ。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from .config import GraphConfig
from .extraction import ExtractedPage

try:  # pragma: no cover - optional dependency
    import networkx as nx  # type: ignore
    from networkx.algorithms.community import greedy_modularity_communities  # type: ignore
except Exception:  # pragma: no cover
    nx = None  # type: ignore[misc]
    greedy_modularity_communities = None  # type: ignore[misc]

try:  # pragma: no cover - optional dependency
    from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
except Exception:  # pragma: no cover
    TfidfVectorizer = None  # type: ignore[misc]

try:  # pragma: no cover - optional dependency
    from slugify import slugify  # type: ignore
except Exception:  # pragma: no cover
    def slugify(value: str) -> str:  # type: ignore[misc]
        return "-".join(value.lower().split())


@dataclass(slots=True)
class Cluster:
    """関連性の高いページをまとめたグループ。"""

    cluster_id: str
    label: str
    slug: str
    page_ids: list[str]


class SiteGraph:
    """抽出済みページからサイトグラフを構築します。"""

    def __init__(self, config: GraphConfig) -> None:
        self._config = config

    def cluster(self, pages: Sequence[ExtractedPage]) -> list[Cluster]:
        if not pages:
            return []
        adjacency = self._build_adjacency(pages)
        groups = self._cluster_with_networkx(adjacency)
        if not groups:
            groups = self._cluster_by_directory(pages)
        clusters: list[Cluster] = []
        used_slugs: set[str] = set()
        for idx, group in enumerate(groups, start=1):
            page_ids = sorted(group)
            label = self._infer_label([self._page_by_id(pid, pages).markdown for pid in page_ids])
            raw_slug = slugify(label) if label else ""
            slug = self._ensure_unique_slug(raw_slug, used_slugs, idx)
            cluster_id = f"cl_{slug}"
            clusters.append(Cluster(cluster_id=cluster_id, label=label or f"Cluster {idx}", slug=slug, page_ids=page_ids))
        return clusters

    # Helpers ----------------------------------------------------------

    def _build_adjacency(self, pages: Sequence[ExtractedPage]) -> dict[str, set[str]]:
        adjacency: dict[str, set[str]] = defaultdict(set)
        url_to_id = {page.url: page.page_id for page in pages if page.url}
        for page in pages:
            for link in page.links:
                target = url_to_id.get(link)
                if target:
                    adjacency[page.page_id].add(target)
                    adjacency[target].add(page.page_id)
        return adjacency

    def _cluster_with_networkx(self, adjacency: dict[str, set[str]]) -> list[set[str]]:
        if not adjacency or nx is None or greedy_modularity_communities is None:
            return []
        graph = nx.Graph()
        for node, neighbors in adjacency.items():
            graph.add_node(node)
            for neighbor in neighbors:
                graph.add_edge(node, neighbor)
        if graph.number_of_nodes() == 0:
            return []
        communities = list(greedy_modularity_communities(graph))
        groups = [set(map(str, community)) for community in communities if len(community) >= self._config.min_cluster_size]
        if not groups:
            return []
        return groups

    def _cluster_by_directory(self, pages: Sequence[ExtractedPage]) -> list[set[str]]:
        buckets: dict[Path, set[str]] = defaultdict(set)
        for page in pages:
            buckets[page.file_path.parent].add(page.page_id)
        return list(buckets.values())

    def _infer_label(self, documents: Sequence[str]) -> str:
        if not documents:
            return ""
        if TfidfVectorizer is None:
            return documents[0].splitlines()[0][:50] if documents[0] else ""
        try:
            vectorizer = TfidfVectorizer(max_features=self._config.label_tfidf_terms, stop_words="english")
            matrix = vectorizer.fit_transform(documents)
            summed = matrix.sum(axis=0)
            scores = zip(vectorizer.get_feature_names_out(), summed.A1)
            top_terms = [term for term, score in sorted(scores, key=lambda x: x[1], reverse=True) if term]
            return " ".join(top_terms[:3])
        except Exception:
            return documents[0].splitlines()[0][:50] if documents[0] else ""

    def _page_by_id(self, page_id: str, pages: Sequence[ExtractedPage]) -> ExtractedPage:
        for page in pages:
            if page.page_id == page_id:
                return page
        raise KeyError(page_id)

    def _ensure_unique_slug(self, slug: str, used: set[str], idx: int) -> str:
        base = slug or f"cluster-{idx:02d}"
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base}-{suffix:02d}"
            suffix += 1
        used.add(candidate)
        return candidate
