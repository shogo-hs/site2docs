"""サイトグラフを構築してクラスタリングするユーティリティ。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Sequence
from urllib.parse import urlparse

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
        if groups:
            groups = self._refine_large_network_groups(groups, pages)
        if not groups:
            pattern_groups, remaining = self._cluster_by_url_pattern(pages)
            if pattern_groups:
                groups = pattern_groups
                if remaining:
                    remaining_pages = [page for page in pages if page.page_id in remaining]
                    if remaining_pages:
                        groups.extend(self._cluster_by_directory_groups(remaining_pages))
            else:
                groups = self._cluster_by_directory_groups(pages)
        groups = self._merge_small_groups(groups, pages)
        if not groups and pages:
            groups = [set(page.page_id for page in pages)]
        clusters: list[Cluster] = []
        used_slugs: set[str] = set()
        page_lookup = {page.page_id: page for page in pages}
        for idx, group in enumerate(groups, start=1):
            page_ids = sorted(group)
            ordered_pages = [page_lookup[pid] for pid in page_ids if pid in page_lookup]
            label = self._infer_label(ordered_pages)
            raw_slug = slugify(label) if label else ""
            slug = self._ensure_unique_slug(raw_slug, used_slugs, idx)
            cluster_id = f"cl_{slug}"
            clusters.append(
                Cluster(
                    cluster_id=cluster_id,
                    label=label or f"Cluster {idx}",
                    slug=slug,
                    page_ids=page_ids,
                )
            )
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

    def _refine_large_network_groups(self, groups: list[set[str]], pages: Sequence[ExtractedPage]) -> list[set[str]]:
        threshold = max(self._config.max_network_cluster_size, self._config.min_cluster_size)
        if threshold <= 0:
            return groups
        lookup = {page.page_id: page for page in pages}
        refined: list[set[str]] = []
        for group in groups:
            if len(group) <= threshold:
                refined.append(group)
                continue
            subset_pages = [lookup[pid] for pid in group if pid in lookup]
            if not subset_pages:
                continue
            pattern_groups, remaining = self._cluster_by_url_pattern(subset_pages)
            if pattern_groups:
                refined.extend(pattern_groups)
                if remaining:
                    remaining_pages = [lookup[pid] for pid in remaining if pid in lookup]
                    if remaining_pages:
                        refined.extend(self._cluster_by_directory_groups(remaining_pages))
                continue
            refined.extend({pid} for pid in group)
        return refined

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

    def _cluster_by_url_pattern(self, pages: Sequence[ExtractedPage]) -> tuple[list[set[str]], set[str]]:
        max_depth = max(1, self._config.url_pattern_depth)
        best_groups: list[set[str]] = []
        best_remaining: set[str] = set()
        for depth in range(max_depth, 0, -1):
            groups, remaining = self._cluster_by_url_pattern_with_depth(pages, depth)
            if groups and not self._all_singleton_groups(groups):
                return groups, remaining
            if groups and not best_groups:
                best_groups, best_remaining = groups, remaining
        return best_groups, best_remaining

    def _cluster_by_url_pattern_with_depth(self, pages: Sequence[ExtractedPage], depth: int) -> tuple[list[set[str]], set[str]]:
        buckets: dict[str, set[str]] = defaultdict(set)
        for page in pages:
            pattern = self._extract_url_pattern(page.url, depth)
            if not pattern:
                continue
            buckets[pattern].add(page.page_id)
        if not buckets:
            return [], set()
        groups: list[set[str]] = []
        assigned: set[str] = set()
        for pattern in sorted(buckets):
            members = buckets[pattern]
            if len(members) >= self._config.min_cluster_size:
                group = set(members)
                groups.append(group)
                assigned.update(group)
        remaining = {page.page_id for page in pages if page.page_id not in assigned}
        return groups, remaining

    def _all_singleton_groups(self, groups: Sequence[set[str]]) -> bool:
        return all(len(group) == 1 for group in groups)

    def _cluster_by_directory_groups(self, pages: Sequence[ExtractedPage]) -> list[set[str]]:
        depth = max(1, self._config.directory_cluster_depth)
        buckets: dict[str, set[str]] = defaultdict(set)
        for page in pages:
            key = self._directory_key(page.file_path, depth)
            buckets[key].add(page.page_id)
        groups: list[set[str]] = []
        threshold = max(2, self._config.min_cluster_size)
        for key in sorted(buckets):
            members = buckets[key]
            if len(members) >= threshold:
                group = set(members)
                groups.append(group)
        return groups

    def _merge_small_groups(self, groups: list[set[str]], pages: Sequence[ExtractedPage]) -> list[set[str]]:
        threshold = max(2, self._config.min_cluster_size)
        if self._config.allow_singleton_clusters or threshold <= 1:
            return groups
        lookup = {page.page_id: page for page in pages}
        large = [group for group in groups if len(group) >= threshold]
        small_ids: list[str] = [pid for group in groups if len(group) < threshold for pid in group]
        if not small_ids:
            return large
        buckets: dict[str, list[str]] = defaultdict(list)
        for pid in small_ids:
            page = lookup.get(pid)
            if page is None:
                continue
            key = self._directory_key(page.file_path, depth=0)
            buckets[key].append(pid)
        merged: list[set[str]] = []
        leftovers: list[str] = []
        for key in sorted(buckets):
            members = buckets[key]
            if len(members) >= threshold:
                merged.append(set(members))
            else:
                leftovers.extend(members)
        if leftovers:
            merged.append(set(leftovers))
        return large + merged

    def _directory_key(self, file_path: Path, depth: int) -> str:
        parts = file_path.parts
        depth = max(0, depth)
        host = ""
        host_index = -1
        try:
            site_idx = parts.index("site_backup")
            candidate = site_idx + 1
            if candidate < len(parts):
                host = parts[candidate]
                host_index = candidate
        except ValueError:
            pass
        if host_index == -1:
            for idx, segment in enumerate(parts):
                lowered = segment.lower()
                if "." in segment and not lowered.endswith((".html", ".htm")):
                    host = segment
                    host_index = idx
                    break
        rel_parts = parts[host_index + 1 :] if host_index >= 0 else parts
        segments: list[str] = []
        for segment in rel_parts:
            lowered = segment.lower()
            if lowered.endswith((".html", ".htm")):
                break
            segments.append(segment)
            if depth and len(segments) >= depth:
                break
        if depth and not segments and rel_parts:
            segments.append(rel_parts[0])
        key_segments = [host] if depth == 0 else ([host] + segments if host else segments)
        if depth == 0 and not host:
            key_segments = ["root"]
        return "/".join(key_segments) if key_segments else str(file_path.parent)

    def _extract_url_pattern(self, url: str, depth: int) -> str:
        if not url:
            return ""
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return ""
        segments = [segment for segment in parsed.path.split("/") if segment]
        normalized = [self._normalize_url_segment(segment) for segment in segments]
        normalized = [segment for segment in normalized if segment]
        if not normalized or depth <= 0:
            return ""
        actual_depth = max(1, min(depth, len(normalized)))
        pattern_segments = normalized[:actual_depth]
        pattern = "/".join(pattern_segments)
        base = parsed.netloc or ""
        return f"{base}/{pattern}" if base else pattern

    def _normalize_url_segment(self, segment: str) -> str:
        cleaned = segment.strip().lower()
        if not cleaned:
            return ""
        if "." in cleaned:
            cleaned = cleaned.split(".")[0]
        if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", cleaned):
            return "{uuid}"
        digit_count = sum(ch.isdigit() for ch in cleaned)
        if digit_count and digit_count == len(cleaned):
            return "{num}"
        if digit_count >= 3 and digit_count / max(len(cleaned), 1) >= 0.5:
            cleaned = re.sub(r"\d+", "{num}", cleaned)
        cleaned = re.sub(r"[^a-z0-9{}-]+", "-", cleaned)
        cleaned = cleaned.strip("-")
        return cleaned

    def _infer_label(self, pages: Sequence[ExtractedPage]) -> str:
        if not pages:
            return ""
        text_label = self._infer_label_from_text(pages)
        if text_label:
            return text_label
        url_label = self._infer_label_from_url_prefix(pages)
        if url_label:
            return url_label
        first = pages[0].markdown.splitlines()[0] if pages[0].markdown else ""
        return first[:50]

    def _infer_label_from_text(self, pages: Sequence[ExtractedPage]) -> str:
        documents = [page.markdown for page in pages if page.markdown.strip()]
        if not documents:
            return ""
        if TfidfVectorizer is None:
            headline = documents[0].splitlines()[0] if documents[0] else ""
            return headline[:50]
        try:
            vectorizer_kwargs: dict[str, Any] = {
                "max_features": self._config.label_tfidf_terms,
            }
            if self._config.label_token_pattern:
                vectorizer_kwargs["token_pattern"] = self._config.label_token_pattern
            language = self._detect_language(documents)
            stop_words: Any
            if language == "en":
                stop_words = "english"
            elif language == "ja":
                stop_words = list(self._config.label_stop_words)
            else:
                stop_words = None
            if stop_words:
                vectorizer_kwargs["stop_words"] = stop_words
            vectorizer = TfidfVectorizer(**vectorizer_kwargs)
            matrix = vectorizer.fit_transform(documents)
            summed = matrix.sum(axis=0)
            scores = zip(vectorizer.get_feature_names_out(), summed.A1)
            top_terms = [term for term, score in sorted(scores, key=lambda x: x[1], reverse=True) if term]
            return " ".join(top_terms[:3])
        except Exception:
            headline = documents[0].splitlines()[0] if documents[0] else ""
            return headline[:50]

    def _detect_language(self, documents: Sequence[str]) -> str:
        sample = "".join(documents)[:5000]
        if not sample:
            return ""
        japanese = sum(1 for char in sample if self._is_japanese_char(char))
        latin = sum(1 for char in sample if char.isalpha() and "a" <= char.lower() <= "z")
        total = sum(1 for char in sample if char.isalpha())
        if total == 0:
            return ""
        if japanese / total >= 0.2:
            return "ja"
        if latin / total >= 0.5:
            return "en"
        return ""

    def _is_japanese_char(self, char: str) -> bool:
        return (
            "一" <= char <= "龥"
            or "ぁ" <= char <= "ゖ"
            or "ァ" <= char <= "ヺ"
            or char == "ー"
        )

    def _infer_label_from_url_prefix(self, pages: Sequence[ExtractedPage]) -> str:
        http_pages = [page for page in pages if page.url.startswith(("http://", "https://"))]
        if not http_pages:
            return ""
        parsed_pages = [urlparse(page.url) for page in http_pages]
        hosts = [parsed.netloc for parsed in parsed_pages if parsed.netloc]
        host = hosts[0] if hosts and all(item == hosts[0] for item in hosts) else ""
        path_segments: list[list[str]] = []
        for parsed in parsed_pages:
            segments = [segment for segment in parsed.path.split("/") if segment]
            path_segments.append(segments)
        common: list[str] = []
        min_length = min((len(segments) for segments in path_segments if segments), default=0)
        for index in range(min_length):
            candidate = path_segments[0][index]
            if all(len(segments) > index and segments[index] == candidate for segments in path_segments):
                common.append(candidate)
            else:
                break
        if not (host or common):
            return ""
        if host and common:
            return f"{host}/{'/'.join(common)}"
        if host:
            return host
        return "/".join(common)

    def _ensure_unique_slug(self, slug: str, used: set[str], idx: int) -> str:
        base = slug or f"cluster-{idx:02d}"
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base}-{suffix:02d}"
            suffix += 1
        used.add(candidate)
        return candidate
