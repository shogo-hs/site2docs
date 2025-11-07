# site2docs

site2docs は、アーカイブ済みのウェブサイトから静的なナレッジベースを生成するツールです。保存された HTML ファイルをレンダリングし、記事風のコンテンツを抽出し、内部リンクを解析して関連ページをクラスタ化し、最終的に Markdown ドキュメントと知識ベースを記述するマニフェストを出力します。

## 特長

- Playwright を用いた任意のレンダリングにより、動的要素を展開可能。
- 折りたたみやアコーディオン、`details` 要素などをヒューリスティックに自動展開し、必要に応じて `--expand-texts` 指定で補完。
- CPU/タスク数から自動推定される Playwright 並列レンダリング（必要に応じて `--render-concurrency` で上書き可能）。
- `file://` で保存されたアーカイブから canonical / OG URL を復元し、元のサイト階層とリンク関係を活かしたクラスタリングを実現。
- ローカルHTMLに合わせて Playwright の待機条件・外部リソースを自動調整し、タイムアウト時は設定を緩和した再試行を行ったうえで安全にフォールバック。
- `--allow-render-fallback` を明示的に指定した場合のみ、再試行後も失敗したページをローカルHTMLのまま処理（デフォルトでは例外を送出してユーザー判断を促します）。
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

`--expand-texts` は任意指定です。英語・日本語・スペイン語など主要言語の代表的なラベルは既にデフォルトでカバーしており、独自の文言だけを追加で渡せば既定リストに自動でマージされます。

Playwright レンダリングの並列度はコア数と入力件数から自動推定されるため、通常はパラメータ調整なしで最適化されます。より厳密に制御したい場合のみ `--render-concurrency` で上書きしてください。

```
uv run site2docs \
  --input ./site_backup \
  --out ./output \
  --render-concurrency 6
```

Playwright でのレンダリングに失敗しても強制的に処理を継続したい場合は明示的に `--allow-render-fallback` を付けてください。指定しない場合は失敗時点でエラーになり、ユーザーが原因を調査したうえで方針を決められるようになっています。

進捗をリアルタイムで確認したい場合は `--verbose` を併用してください。

```
uv run site2docs \
  --input ./site_backup \
  --out ./output \
  --verbose
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

`logs/build_summary.json` にはビルド工程（検出・レンダリング・抽出・クラスタリング・出力）の進捗が随時追記されるため、`tail -f` で監視することで処理状況を把握できます。

## サイト階層の復元

アーカイブ済み HTML は `file://` スキームで保存されていても、`link[rel=canonical]` や `meta[property=og:url]`、保存先パスから元の `https://<host>/...` を復元します。これにより、

- 内部リンク解決とリンクグラフ解析がオリジナル URL で行われ、階層構造を保ったクラスタリングが可能。
- `manifest.json` の `cluster_id` / `cluster_label` がサイトの導線に沿う形でまとまり、ドキュメント同士の参照関係を再構築しやすい。

独自のアーカイブ形式で canonical が取得できない場合でも、`site_backup/<host>/...` のディレクトリ構造からホスト名とパスを導出して正規化します。
