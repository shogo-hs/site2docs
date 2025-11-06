"""site2docs パイプラインの設定モデル群。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, Sequence


def default_timestamp() -> datetime:
    """メタデータ用に現在時刻 (UTC) を返します。"""

    return datetime.now(timezone.utc)


@dataclass(slots=True)
class RenderConfig:
    """コンテンツ抽出前に適用するレンダリング設定。"""

    scroll_pause: float = 0.2
    max_scroll_iterations: int = 20
    expand_texts: Sequence[str] = ("more", "show more", "もっと見る", "詳細", "展開")
    wait_until: str = "networkidle"
    render_timeout: float = 30.0
    auto_expand_candidates: bool = True


@dataclass(slots=True)
class ExtractionConfig:
    """テキスト抽出および整形の設定。"""

    readability: bool = True
    trafilatura: bool = True
    preserve_headings: bool = True
    fallback_plain_text: bool = True


@dataclass(slots=True)
class GraphConfig:
    """サイトグラフ構築とクラスタリングの設定。"""

    min_cluster_size: int = 1
    label_tfidf_terms: int = 5
    url_pattern_depth: int = 3


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
    ) -> "BuildConfig":
        render_config = RenderConfig(
            expand_texts=tuple(t.strip() for t in (expand_texts or ())) or RenderConfig().expand_texts,
        )
        return cls(
            input_dir=input_dir,
            output=OutputConfig(output_dir),
            render=render_config,
        )
