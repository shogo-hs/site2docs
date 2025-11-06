"""site2docs のコマンドラインインターフェース。"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Iterable

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
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv)
    _validate_args(args)
    _configure_logging(args.verbose)
    config = BuildConfig.from_args(args.input_dir, args.output_dir, expand_texts=_parse_expand_texts(args.expand_texts))
    result = build_documents(config)
    summary = {
        "pages": len(result.pages),
        "clusters": len(result.clusters),
        "output": str(config.output.root),
    }
    print(json.dumps(summary, ensure_ascii=False))


def _validate_args(args: argparse.Namespace) -> None:
    errors: list[str] = []
    if not args.input_dir.exists():
        errors.append(f"[エラー] 入力ディレクトリが見つかりません: {args.input_dir}")
    elif not args.input_dir.is_dir():
        errors.append(f"[エラー] 入力パスはディレクトリではありません: {args.input_dir}")

    if args.output_dir.exists() and not args.output_dir.is_dir():
        errors.append(f"[エラー] 出力パスがディレクトリではありません: {args.output_dir}")

    if errors:
        for message in errors:
            print(message, file=sys.stderr)
        print("入力・出力パスを確認し、存在するディレクトリを指定してください。", file=sys.stderr)
        raise SystemExit(2)

    args.input_dir = args.input_dir.resolve()
    args.output_dir = args.output_dir.resolve()


def _configure_logging(verbose: bool) -> None:
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    main()
