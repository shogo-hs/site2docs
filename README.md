# site2docs

[![version](https://img.shields.io/badge/version-0.1.0-blue.svg)](pyproject.toml)

> アーカイブ済み HTML を Playwright で再現し、知識ベースに最適化された Markdown と manifest をワンコマンドで生成するツールキット。

英語版 README は [README.en.md](README.en.md) を参照してください。

## 概要
site2docs は、`site_backup/` に保存されたローカル HTML 群を解析し、リンク構造・本文・取得日時を再整理した静的ナレッジベースを構築します。RAG 導入前の資料整備や、保守が止まった社内ポータルの再編など「情報を壊さずに読みやすく整理したい」シーンを想定しています。

## 主なユースケース
- 社内外ドキュメントのアーカイブを Markdown & manifest へ移行し、検索基盤や CMS へ安全に取り込む。
- Playwright による自動展開で、JS 依存の FAQ / サポートサイトを静的ファイル化する。
- RAG 前処理として「クリーンなテキスト」「由来メタデータ」「クラスタ情報」をまとめて生成する。

## 機能ハイライト
- **ブラウザレンダリング**: Playwright が `file://` HTML を開き、スクロール・折りたたみ解除・再試行を自動化。失敗時は安全にフォールバックし、必要に応じて `--allow-render-fallback` で処理継続。
- **多段抽出エンジン**: Readability → Trafilatura → BeautifulSoup の順に本文抽出を試行し、見出しや表を保持。最低文字数やセマンティック領域の閾値は `ExtractionConfig` で管理。
- **リンクグラフ・クラスタリング**: NetworkX でサイトグラフを構築し、URL パターン・ディレクトリ深度・TF-IDF に基づいてクラスタラベル/スラッグを自動生成。
- **Markdown + manifest**: 各クラスタを 1 ドキュメントに統合し、YAML フロントマターと出典情報を付与。`manifest.json` にはページ/クラスタ単位のメタデータを保持。
- **進捗可視化**: `logs/build_summary.json` にステージごとの NDJSON ログを書き込み、`--verbose` と合わせて長時間バッチを追跡可能。
- **ハルシネーション抑制**: 生成されたドキュメントの信頼性を `logs/hallucination_report.json` で可視化。クラスタラベルや要約が出典と乖離していないか自動検査します。

## アーキテクチャ概要
```mermaid
flowchart LR
    A[site_backup/*.html] -->|Playwright| B[rendering.PageRenderer]
    B -->|安定化DOM| C[extraction.ContentExtractor]
    C -->|ExtractedPage| D[graphing.SiteGraph]
    D -->|Cluster| E[document.py]
    D -->|Metadata| F[manifest.py]
    E --> G[docs/<slug>.md]
    F --> H[manifest.json]
    A -->|進捗| I[logs/build_summary.json]
```

## 動作要件
- Python 3.11 以上
- [uv](https://github.com/astral-sh/uv)（依存同期・コマンド実行に使用）
- Playwright が動作する OS（Chromium ベースブラウザを自動インストール可能）

## セットアップ
1. 依存関係を同期
   ```bash
   uv sync
   ```
2. Playwright 用ブラウザを初期化（初回のみ）
   ```bash
   uv run playwright install chromium
   ```
3. 動作確認
   ```bash
   uv run site2docs --help
   ```

## 入力データの準備
`site_backup/` にはアーカイブ済みの HTML をホストごとに配置します。既存ポータルのバックアップを持っていない場合は、以下のいずれかの方法でサンプルを用意してください。

- **既存アーカイブをコピーする:** `wget --mirror` や社内バックアップから取得した HTML 群を `site_backup/<project>/` に展開します。CSS/画像などの相対パスも保つことで Playwright がレイアウトを再現できます。
- **チュートリアル用サンプルを生成する:**
  ```bash
  mkdir -p site_backup/sample_site
  cat <<'HTML' > site_backup/sample_site/index.html
  <!doctype html>
  <html lang="ja">
    <head>
      <meta charset="utf-8" />
      <title>Sample Service</title>
    </head>
    <body>
      <h1>サイト移行の手引き</h1>
      <p>RAG 前処理のために Markdown を生成するサンプルページです。</p>
      <a href="./faq.html">FAQ はこちら</a>
    </body>
  </html>
  HTML
  cat <<'HTML' > site_backup/sample_site/faq.html
  <!doctype html>
  <html lang="ja">
    <head>
      <meta charset="utf-8" />
      <title>FAQ</title>
    </head>
    <body>
      <h1>よくある質問</h1>
      <details>
        <summary>Playwright が失敗する場合</summary>
        <p>再実行または --allow-render-fallback を検討します。</p>
      </details>
    </body>
  </html>
  HTML
  ```
  2 枚の HTML を用意するだけでもクラスタリングや manifest の挙動を確認できます。

## クイックスタート
最小構成で Markdown と manifest を生成する例です。
```bash
uv run site2docs \
  --input ./site_backup/sample_site \
  --out ./output/sample_site \
  --verbose
```
- `output/sample_site/docs/*.md` にクラスタ単位のドキュメントが作成されます（例: `output/sample_site/docs/example-cluster.md`）。
- `output/sample_site/manifest.json` にはページ ID、クラスタ ID、URL、取得時刻が格納されます。
- `output/sample_site/logs/build_summary.json` を `tail -f` すると、`discovered → rendered → extracting → clustering → completed` の進捗が確認できます。

## 設定リファレンス
高度な調整が必要な場合は、`src/site2docs/config.py` の設定モデルを直接参照できます。主なエントリポイントは以下のとおりです。

| 設定クラス | 役割 | 主な項目 | 参照先 |
| --- | --- | --- | --- |
| `RenderConfig` | Playwright のレンダリング制御 | `max_concurrency` / `expand_texts` / `allow_plain_fallback` | `src/site2docs/config.py` |
| `ExtractionConfig` | 本文抽出と閾値設定 | `min_content_characters` / `semantic_body_fallback` | `src/site2docs/config.py` |
| `GraphConfig` | グラフ構築とクラスタリング | `label_token_pattern` / `min_cluster_size` / `url_pattern_depth` | `src/site2docs/config.py` |
| `BuildConfig` | CLI 引数から全体設定を組み立て | `from_args()` で CLI 指定を反映 | `src/site2docs/config.py` |

CLI から直接指定できない項目を変更したい場合は、以下のいずれかを検討してください。

- `pyproject.toml` の `tool.site2docs` セクションを追加し、自前スクリプトから `BuildConfig` を生成する。
- `src/site2docs/config.py` を参考にカスタムスクリプトを作成し、`Site2DocsBuilder` を呼び出す（例: `python -m site2docs.builder` 形式）。

## CLI オプション一覧
| オプション | 既定値 | 説明 |
| --- | --- | --- |
| `--input` | (必須) | HTML を含むディレクトリ。`site_backup/` 以下の階層構造を前提。 |
| `--out` | (必須) | 生成物の出力先。既存ファイルは再利用し、`docs/` `logs/` を自動作成。 |
| `--expand-texts` | 内蔵辞書 | 折りたたみ解除に使うボタン文言をカンマ区切りで追加。既定リストとマージされます。 |
| `--render-concurrency` | 自動推定 | Playwright 同時ページ数。CPU コア数と入力件数からの推定値を上書きする際に指定。 |
| `--allow-render-fallback` | `false` | レンダリング再試行後も失敗したページをローカル HTML のまま処理して継続。指定しない場合は例外で停止。 |
| `--verbose` | `false` | INFO ログを標準出力へ出し、進捗をリアルタイムに確認。 |
| `--no-hallucination-check` | `false` | 品質検証ノードを無効化し、ハルシネーションレポートを省略。 |
| `--hallucination-min-chars` | `120` | 1 ページあたりに必要な最小文字数。下回るとレポートに警告を追記。 |
| `--hallucination-label-token-length` | `4` | ラベル検証に使う最小トークン長。該当語が本文に無い場合に警告。 |

## 出力構成
```
<out>/
  docs/
    <cluster-slug>.md     # YAMLフロントマター + 概要 + 目次 + ページ本文
  manifest.json           # pages/clusters のメタデータ
  logs/
    build_summary.json    # NDJSON 形式の進捗ログ
    hallucination_report.json # ハルシネーション検知レポート
```
### Markdown の例 (抜粋)
```markdown
---
doc_id: doc_service-overview
cluster_label: サービス紹介
cluster_slug: service-overview
source_urls:
  - https://example.com/service
created_at: 2025-11-07T00:00:00Z
pages: [pg_001]
---
## サマリー
...
```
### manifest.json の主なフィールド
- `pages[].page_id` / `pages[].url` / `pages[].file_path`
- `pages[].cluster_id` / `clusters[].label` / `clusters[].slug`
- `created_at`: ビルド時刻（UTC）

## ログと可観測性
- `logs/build_summary.json` は 1 行 1 JSON の NDJSON。`stage` フィールドで現在の工程を確認できます。
- `--verbose` を付けると INFO ログが CLI にも出力され、Playwright の進行状況や抽出対象ファイル名が分かります。
- 長時間ジョブでは `tail -f output/<name>/logs/build_summary.json` を別ターミナルで常時監視する運用を推奨します。

### stage フィールドの意味
| stage | 意味 | 主な項目 |
| --- | --- | --- |
| `discovered` | 入力 HTML を走査し終えた直後 | `total_html` |
| `rendering` / `rendered` | Playwright によるレンダリング中 / 完了 | `rendered` / `last_file` |
| `extracting` | 本文抽出ループ | `extracted` / `last_file` |
| `clustering` | グラフ構築とクラスタリング | `clusters` |
| `writing` | Markdown 出力中 | `documents_count` / `last_document` |
| `quality_check` | ハルシネーション検知レポート生成 | `findings` / `report` |
| `completed` | すべての成果物を生成済み | `documents` / `manifest` |

ログが停止した stage を特定できるため、失敗箇所の切り分けに役立ちます。異常終了時は最後のレコードと同じ `stage` の INFO ログを参照してください。

## 高度な設定・運用 Tips
- **独自ボタンの展開**: `--expand-texts "表示する,Show details"` のように追加すると既定辞書へ自動マージされます。
- **並列度の調整**: I/O が遅いファイルシステムでは `--render-concurrency 4` など控えめに設定すると安定します。
- **ラベル抽出のチューニング**: `GraphConfig.label_token_pattern` で TF-IDF のトークン正規表現を上書きでき、日本語や多言語サイトでも意図どおりのクラスタラベルを得られます。
- **フォールバック戦略**: 品質を最優先する場合は `--allow-render-fallback` を付けずに失敗ページを洗い出し、HTML 側を修正して再実行してください。
- **ログローテーション**: 大規模サイトでは `logs/build_summary.json` が数 MB になる場合があります。完了後にアーカイブまたは削除してディスクを管理してください。
- **ハルシネーションレポート**: `logs/hallucination_report.json` の `findings` を参照すると、クラスタラベルと本文のズレや出典 URL 欠落などの警告を RAG ワークフローへ共有できます。

## トラブルシューティング
- **Playwright がブラウザを起動できない**: `uv run playwright install chromium` を実行し、必要な依存パッケージ（libgtk など）が OS に入っているか確認してください。
- **入力ディレクトリが見つからないエラー**: `site_backup/<host>/` の絶対パスを指定し、シンボリックリンクの場合は実体パスを渡してください。
- **抽出結果が空になる**: HTML が 400 文字以下の場合は `ExtractionConfig.min_content_characters` に達しない可能性があります。テンプレートやメタリフレッシュのみのページは除外してください。
- **クラスタが分裂しすぎる**: ルート直下に多数のサブディレクトリがある場合、URL パターン深度を下げるか、リンクを再構築して再アーカイブしてください。
- **Playwright のレンダリングが途中で止まる**: `output/<name>/logs/build_summary.json` で `rendering` ステージの最後に記録された `last_file` を確認し、該当 HTML をブラウザで開いて JavaScript エラーがないか検証します。`--allow-render-fallback` を一時的に有効にして抽出のみ進めると原因切り分けが容易になります。
- **長時間バッチで原因箇所を特定したい**: `completed` 以前で停止した場合、同じ `stage` のログ行を抽出します。例: `jq 'select(.stage=="extracting")' logs/build_summary.json | tail`。`last_file` や `documents_count` が繰り返し同じ値であれば、ループ内の例外が疑われます。

## 開発者向けメモ
- コードは `src/site2docs/` に集約。責務別モジュール（`rendering.py` / `extraction.py` / `graphing.py` / `document.py` / `manifest.py` / `builder.py` / `cli.py`）。
- テスト: `uv run pytest`
- CLI ヘルプ確認: `uv run site2docs --help`
- 依存管理: すべて uv 経由で行い、`pyproject.toml`/`uv.lock` を唯一のソースオブトゥルースとしてください。

## バージョン
- 現行バージョン: **v0.1.0** （`pyproject.toml` の `version` フィールドに追従）
- リリースタグを作成する際は `pyproject.toml` と README のバッジが一致していることを確認してください。

## 関連ドキュメント
- `codex_spec_static_doc_generation.md`: 仕様の背景と期待する出力構成
- `AGENTS.md`: リポジトリ横断のルールセット

## ライセンス
本プロジェクトは MIT License の下で配布されます。詳細はリポジトリ直下の `LICENSE` を参照してください。
