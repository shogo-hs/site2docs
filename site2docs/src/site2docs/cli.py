"""site2docs のコマンドラインインターフェース。"""

from __future__ import annotations

import argparse
import json
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
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv)
    config = BuildConfig.from_args(args.input_dir, args.output_dir, expand_texts=_parse_expand_texts(args.expand_texts))
    result = build_documents(config)
    summary = {
        "pages": len(result.pages),
        "clusters": len(result.clusters),
        "output": str(config.output.root),
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
