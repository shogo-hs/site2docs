# site2docs

site2docs は、アーカイブ済みのウェブサイトから静的なナレッジベースを生成するツールです。保存された HTML ファイルをレンダリングし、記事風のコンテンツを抽出し、内部リンクを解析して関連ページをクラスタ化し、最終的に Markdown ドキュメントと知識ベースを記述するマニフェストを出力します。

## 特長

- Playwright を用いた任意のレンダリングにより、動的要素を展開可能。
- Readability や Trafilatura を活用しつつ、利用できない場合は段階的にフォールバック。
- リンクグラフ解析で関連ページをまとめ、ドキュメント単位へ集約。
- 由来情報を記録した YAML フロントマター付き Markdown を生成。
- ページメタデータとクラスタ情報を保持する JSON マニフェストを出力。

## 開発

Python 実装は `site2docs/src/site2docs` に配置されています。モジュールごとの役割は以下の通りです。

- `config.py`: dataclass ベースの設定オブジェクトとヘルパー。
- `rendering.py`: Playwright を利用した HTML 読み込み・レンダリング。
- `extraction.py`: テキスト・見出し・リンクの抽出処理。
- `graphing.py`: サイトグラフ構築とクラスタリング。
- `document.py`: YAML フロントマター付き Markdown 組み立て。
- `manifest.py`: JSON マニフェスト生成処理。
- `builder.py`: ワークフロー全体を調整するパイプライン。
- `cli.py`: CLI エントリーポイント。

依存関係管理には [uv](https://github.com/astral-sh/uv) を使用します。`site2docs/` ディレクトリで以下のコマンドを実行してください。

```bash
uv sync           # 依存関係をインストール（ネットワーク接続が必要）
uv run site2docs --help
```

## 使い方

```
uv run site2docs \
  --input ./site_backup \
  --out ./output \
  --expand-texts "もっと見る,Show more"
```

出力は指定した `--out` ディレクトリ配下に保存されます。

```
output/
  docs/
    <cluster-slug>.md
  manifest.json
  logs/
```

各 Markdown ドキュメントには、自動生成されたサマリー、見出しが存在する場合の目次、およびクラスタ内の各ページから抽出した本文と出典情報が含まれます。
