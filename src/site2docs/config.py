"""site2docs パイプラインの設定モデル群。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence


def _merge_expand_texts(
    defaults: Sequence[str], extras: Sequence[str]
) -> tuple[str, ...]:
    """既定の文言と追加指定を大文字小文字を無視して結合します。"""

    seen: set[str] = set()
    merged: list[str] = []
    for text in (*defaults, *extras):
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        merged.append(text)
    return tuple(merged)


def default_timestamp() -> datetime:
    """メタデータ用に現在時刻 (UTC) を返します。"""

    return datetime.now(timezone.utc)


@dataclass(slots=True)
class RenderConfig:
    """コンテンツ抽出前に適用するレンダリング設定。"""

    scroll_pause: float = 0.2
    max_scroll_iterations: int = 20
    expand_texts: Sequence[str] = (
        "more",
        "show more",
        "show all",
        "read more",
        "load more",
        "view more",
        "see more",
        "expand",
        "open all",
        "ver mas",
        "ver más",
        "mostrar mas",
        "weiterlesen",
        "もっと見る",
        "さらに表示",
        "詳細",
        "詳細を見る",
        "すべて表示",
        "全て表示",
        "続きを読む",
        "続きを見る",
        "展開",
        "折りたたみ解除",
    )
    wait_until: str = "networkidle"
    render_timeout: float = 30.0
    auto_expand_candidates: bool = True
    max_concurrency: int | None = None
    max_render_attempts: int = 2
    timeout_backoff_factor: float = 1.6
    file_scheme_wait_until: str = "domcontentloaded"
    post_render_delay: float = 0.2
    allow_plain_fallback: bool = False


@dataclass(slots=True)
class ExtractionConfig:
    """テキスト抽出および整形の設定。"""

    readability: bool = True
    trafilatura: bool = True
    preserve_headings: bool = True
    fallback_plain_text: bool = True
    min_content_characters: int = 400
    semantic_body_fallback: bool = True
    semantic_min_length: int = 600
    semantic_length_ratio: float = 1.25
    semantic_min_delta: int = 100


@dataclass(slots=True)
class GraphConfig:
    """サイトグラフ構築とクラスタリングの設定。"""

    min_cluster_size: int = 2
    label_tfidf_terms: int = 5
    label_token_pattern: str | None = r"(?u)[\w一-龥ぁ-んァ-ヶー]+"
    label_stop_words: Sequence[str] = (
        "こと",
        "ため",
        "よう",
        "です",
        "ます",
        "する",
        "いる",
        "ある",
        "なる",
        "この",
        "その",
        "それ",
        "そして",
        "また",
        "など",
        "さらに",
        "しかし",
    )
    url_pattern_depth: int = 3
    max_network_cluster_size: int = 12
    directory_cluster_depth: int = 2
    allow_singleton_clusters: bool = False


@dataclass(slots=True)
class OutputConfig:
    """出力ディレクトリの設定。"""

    root: Path
    docs_dir: Path = field(init=False)
    logs_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.docs_dir = self.root / "docs"
        self.logs_dir = self.root / "logs"


@dataclass(slots=True)
class BuildConfig:
    """ドキュメント生成全体を束ねる設定。"""

    input_dir: Path
    output: OutputConfig
    render: RenderConfig = field(default_factory=RenderConfig)
    extract: ExtractionConfig = field(default_factory=ExtractionConfig)
    graph: GraphConfig = field(default_factory=GraphConfig)
    created_at: datetime = field(default_factory=default_timestamp)

    @classmethod
    def from_args(
        cls,
        input_dir: Path,
        output_dir: Path,
        expand_texts: Optional[Iterable[str]] = None,
        max_concurrency: Optional[int] = None,
        allow_render_fallback: bool = False,
        extraction_overrides: Mapping[str, Any] | None = None,
        graph_overrides: Mapping[str, Any] | None = None,
    ) -> "BuildConfig":
        defaults = RenderConfig()
        render_kwargs: dict[str, Any] = {}
        normalized_texts = tuple(
            text.strip() for text in (expand_texts or ()) if text and text.strip()
        )
        if normalized_texts:
            merged = _merge_expand_texts(defaults.expand_texts, normalized_texts)
            render_kwargs["expand_texts"] = merged
        if max_concurrency is not None:
            render_kwargs["max_concurrency"] = max(1, max_concurrency)
        if allow_render_fallback:
            render_kwargs["allow_plain_fallback"] = True
        render_config = RenderConfig(**render_kwargs)
        extract_config = ExtractionConfig(**(dict(extraction_overrides) if extraction_overrides else {}))
        graph_config = GraphConfig(**(dict(graph_overrides) if graph_overrides else {}))
        return cls(
            input_dir=input_dir,
            output=OutputConfig(output_dir),
            render=render_config,
            extract=extract_config,
            graph=graph_config,
        )
