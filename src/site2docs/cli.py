"""site2docs のコマンドラインインターフェース。"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Iterable

from .builder import build_documents
from .config import BuildConfig


def _parse_expand_texts(raw: str | None) -> Iterable[str]:
    if not raw:
        return ()
    return [chunk.strip() for chunk in raw.split(",") if chunk.strip()]


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="アーカイブ済みサイトから静的ドキュメントを生成します")
    parser.add_argument("--input", dest="input_dir", type=Path, required=True, help="HTML ファイルを含むディレクトリへのパス")
    parser.add_argument("--out", dest="output_dir", type=Path, required=True, help="生成成果物を書き出すディレクトリ")
    parser.add_argument("--expand-texts", dest="expand_texts", type=str, default="", help="自動展開したいボタン文言をカンマ区切りで指定")
    parser.add_argument("--verbose", dest="verbose", action="store_true", help="進捗ログを標準出力へ表示")
    parser.add_argument(
        "--render-launch-options",
        dest="render_launch_options",
        type=str,
        default=None,
        help="Playwright ブラウザの起動オプションを JSON で指定",
    )
    parser.add_argument(
        "--render-concurrency",
        dest="render_concurrency",
        type=int,
        default=None,
        help="Playwright レンダリング時の同時ブラウザページ数 (省略時は CPU/タスク数から自動推定)",
    )
    parser.add_argument(
        "--allow-render-fallback",
        dest="allow_render_fallback",
        action="store_true",
        help="Playwright で再試行しても失敗したページを最終手段としてローカルHTMLのまま処理する",
    )

    extraction_group = parser.add_argument_group("抽出設定")
    extraction_group.add_argument(
        "--min-content-chars",
        dest="min_content_characters",
        type=int,
        default=None,
        help="本文として採用するために必要な最小文字数",
    )
    extraction_group.add_argument(
        "--semantic-min-length",
        dest="semantic_min_length",
        type=int,
        default=None,
        help="セマンティック補完を試行する本文の最小文字数",
    )
    extraction_group.add_argument(
        "--semantic-length-ratio",
        dest="semantic_length_ratio",
        type=float,
        default=None,
        help="セマンティック補完で採用する本文長の倍率しきい値",
    )
    extraction_group.add_argument(
        "--semantic-min-delta",
        dest="semantic_min_delta",
        type=int,
        default=None,
        help="セマンティック補完で必要となる最小文字数差分",
    )
    extraction_group.add_argument(
        "--extract-concurrency",
        dest="extract_concurrency",
        type=int,
        default=None,
        help="抽出処理の並列実行数 (省略時は CPU 数から自動推定)",
    )
    extraction_group.add_argument(
        "--no-readability",
        dest="no_readability",
        action="store_true",
        help="Readability による抽出を無効化する",
    )
    extraction_group.add_argument(
        "--no-trafilatura",
        dest="no_trafilatura",
        action="store_true",
        help="Trafilatura による抽出を無効化する",
    )
    extraction_group.add_argument(
        "--no-semantic-fallback",
        dest="no_semantic_fallback",
        action="store_true",
        help="セマンティック補完を無効化する",
    )

    graph_group = parser.add_argument_group("クラスタリング設定")
    graph_group.add_argument(
        "--min-cluster-size",
        dest="min_cluster_size",
        type=int,
        default=None,
        help="クラスタとして採用するために必要なページ数",
    )
    graph_group.add_argument(
        "--allow-singleton-clusters",
        dest="allow_singleton_clusters",
        action="store_true",
        help="単一ページのクラスタ生成を許可する",
    )
    graph_group.add_argument(
        "--max-network-cluster-size",
        dest="max_network_cluster_size",
        type=int,
        default=None,
        help="NetworkX によるクラスタリングで許容する最大クラスタサイズ",
    )
    graph_group.add_argument(
        "--directory-cluster-depth",
        dest="directory_cluster_depth",
        type=int,
        default=None,
        help="ディレクトリ構造ベースのグルーピングを行う階層の深さ",
    )
    graph_group.add_argument(
        "--url-pattern-depth",
        dest="url_pattern_depth",
        type=int,
        default=None,
        help="URL パターンによるグルーピングを試行する深さ",
    )
    graph_group.add_argument(
        "--label-tfidf-terms",
        dest="label_tfidf_terms",
        type=int,
        default=None,
        help="クラスタラベルに採用する TF-IDF キーワード数",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv)
    _validate_args(args)
    try:
        launch_options = _parse_launch_options(args.render_launch_options)
    except ValueError as exc:
        print(f"[エラー] --render-launch-options: {exc}", file=sys.stderr)
        raise SystemExit(2)
    _configure_logging(args.verbose)
    extraction_overrides = _collect_extraction_overrides(args)
    graph_overrides = _collect_graph_overrides(args)
    config = BuildConfig.from_args(
        args.input_dir,
        args.output_dir,
        expand_texts=_parse_expand_texts(args.expand_texts),
        max_concurrency=args.render_concurrency,
        allow_render_fallback=args.allow_render_fallback,
        launch_options=launch_options,
        extraction_overrides=extraction_overrides,
        graph_overrides=graph_overrides,
    )
    result = build_documents(config)
    summary = {
        "pages": len(result.pages),
        "clusters": len(result.clusters),
        "output": str(config.output.root),
        "render_fallback_pages": result.render_fallback_pages,
    }
    if result.render_fallback_reasons:
        summary["render_fallback_reasons"] = list(result.render_fallback_reasons)
    print(json.dumps(summary, ensure_ascii=False))


def _validate_args(args: argparse.Namespace) -> None:
    errors: list[str] = []
    if not args.input_dir.exists():
        errors.append(f"[エラー] 入力ディレクトリが見つかりません: {args.input_dir}")
    elif not args.input_dir.is_dir():
        errors.append(f"[エラー] 入力パスはディレクトリではありません: {args.input_dir}")

    if args.output_dir.exists() and not args.output_dir.is_dir():
        errors.append(f"[エラー] 出力パスがディレクトリではありません: {args.output_dir}")

    if args.render_concurrency is not None and args.render_concurrency < 1:
        errors.append("[エラー] --render-concurrency には 1 以上の整数を指定してください。")

    if args.min_content_characters is not None and args.min_content_characters < 0:
        errors.append("[エラー] --min-content-chars には 0 以上の整数を指定してください。")
    if args.semantic_min_length is not None and args.semantic_min_length < 0:
        errors.append("[エラー] --semantic-min-length には 0 以上の整数を指定してください。")
    if args.semantic_length_ratio is not None and args.semantic_length_ratio <= 0:
        errors.append("[エラー] --semantic-length-ratio には 0 より大きい数値を指定してください。")
    if args.semantic_min_delta is not None and args.semantic_min_delta < 0:
        errors.append("[エラー] --semantic-min-delta には 0 以上の整数を指定してください。")
    if args.extract_concurrency is not None and args.extract_concurrency < 1:
        errors.append("[エラー] --extract-concurrency には 1 以上の整数を指定してください。")
    if args.min_cluster_size is not None and args.min_cluster_size < 1:
        errors.append("[エラー] --min-cluster-size には 1 以上の整数を指定してください。")
    if args.max_network_cluster_size is not None and args.max_network_cluster_size < 1:
        errors.append(
            "[エラー] --max-network-cluster-size には 1 以上の整数を指定してください。"
        )
    if args.directory_cluster_depth is not None and args.directory_cluster_depth < 0:
        errors.append(
            "[エラー] --directory-cluster-depth には 0 以上の整数を指定してください。"
        )
    if args.url_pattern_depth is not None and args.url_pattern_depth < 0:
        errors.append("[エラー] --url-pattern-depth には 0 以上の整数を指定してください。")
    if args.label_tfidf_terms is not None and args.label_tfidf_terms < 1:
        errors.append("[エラー] --label-tfidf-terms には 1 以上の整数を指定してください。")

    if errors:
        for message in errors:
            print(message, file=sys.stderr)
        print("入力・出力パスを確認し、存在するディレクトリを指定してください。", file=sys.stderr)
        raise SystemExit(2)

    args.input_dir = args.input_dir.resolve()
    args.output_dir = args.output_dir.resolve()


def _collect_extraction_overrides(args: argparse.Namespace) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    if args.min_content_characters is not None:
        overrides["min_content_characters"] = args.min_content_characters
    if args.semantic_min_length is not None:
        overrides["semantic_min_length"] = args.semantic_min_length
    if args.semantic_length_ratio is not None:
        overrides["semantic_length_ratio"] = args.semantic_length_ratio
    if args.semantic_min_delta is not None:
        overrides["semantic_min_delta"] = args.semantic_min_delta
    if args.extract_concurrency is not None:
        overrides["max_workers"] = args.extract_concurrency
    if args.no_readability:
        overrides["readability"] = False
    if args.no_trafilatura:
        overrides["trafilatura"] = False
    if args.no_semantic_fallback:
        overrides["semantic_body_fallback"] = False
    return overrides


def _collect_graph_overrides(args: argparse.Namespace) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    if args.min_cluster_size is not None:
        overrides["min_cluster_size"] = args.min_cluster_size
    if args.allow_singleton_clusters:
        overrides["allow_singleton_clusters"] = True
    if args.max_network_cluster_size is not None:
        overrides["max_network_cluster_size"] = args.max_network_cluster_size
    if args.directory_cluster_depth is not None:
        overrides["directory_cluster_depth"] = args.directory_cluster_depth
    if args.url_pattern_depth is not None:
        overrides["url_pattern_depth"] = args.url_pattern_depth
    if args.label_tfidf_terms is not None:
        overrides["label_tfidf_terms"] = args.label_tfidf_terms
    return overrides


def _configure_logging(verbose: bool) -> None:
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")


def _parse_launch_options(raw: str | None) -> dict[str, Any] | None:
    if raw is None or not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:  # pragma: no cover - json error path
        raise ValueError(f"JSON の解析に失敗しました ({exc.msg})") from exc
    if not isinstance(parsed, dict):
        raise ValueError("JSON オブジェクトを指定してください。")
    return parsed


if __name__ == "__main__":
    main()
