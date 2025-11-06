# サイトバックアップから静的ナレッジドキュメントを生成する仕様書（Codex向け）

## 目的
RAG導入前段階として、保存済みHTML群（JavaScript含むWebページ）を**人間可読なドキュメント群**に整理・統合し、  
関連ページをまとめた「知識ベース」として体系化する。  
この段階では**チャンク分割や埋め込み生成は行わず**、情報構造の正規化とドキュメント化のみに焦点を置く。

---

## スコープ
### ✅ 対象に含む
- ローカル保存済みの `.html` ファイルと付随フォルダ（画像/CSS/JS）。  
- HTML同士のリンク関係からサイトマップを自動抽出。  
- 関連するページをクラスタリングして1ドキュメントに統合（Markdown形式）。  
- JavaScriptで動的展開される要素も、Playwright等で**実際に展開した後のDOM**から抽出。  
- 出典URL・ファイルパス・抽出日時を保持し、追跡可能に記録。  

### ❌ 対象外
- RAG向けのベクトル化・チャンク分割・embedding生成。
- JSコード実行そのもの（例：Ajax通信結果の取得など）。  
- 認証・ユーザ操作を要するページの自動収集。

---

## 出力構成
```
output/
  docs/
    <cluster-slug-1>.md
    <cluster-slug-2>.md
  manifest.json
  sitemap_graph.png   # 任意
  logs/
```
### 各Markdown
- YAML Frontmatter  
  ```yaml
  doc_id: "doc_xxx"
  cluster_label: "サポートFAQ"
  cluster_slug: "support-faq"
  source_urls: [...]
  created_at: "2025-11-06T00:00:00+09:00"
  pages: ["pg_001", "pg_002", ...]
  ```
- 本文構成  
  1. 概要（自動生成）  
  2. 目次（H2/H3見出しから）  
  3. 各ページ本文（出典URL・ファイルパス・取得日時付き）

---

## 主な処理フロー
```
[入力HTML群] 
   ↓
[Playwrightでレンダリング＆展開]
   ↓
[本文抽出 (readability-lxml / trafilatura)]
   ↓
[リンク解析 → サイトグラフ構築 (networkx)]
   ↓
[クラスタリング → クラスタごとMarkdown出力]
   ↓
[manifest.json生成・ログ出力]
```

---

## 機能要件
### 1. レンダリング・展開
- PlaywrightでHTMLを開き、次を自動実行：  
  - ページ末尾までスクロール（lazy-load対策）  
  - `aria-expanded="false"`や「もっと見る」「Show more」等のボタンを自動クリック  
  - すべてのDOMが安定した後に `outerHTML` を取得  
- ローカルHTMLでも動作可能。

### 2. 本文抽出
- `readability-lxml` でDOM本文を抽出、失敗時は `trafilatura` にフォールバック。
- 見出し（H1/H2/H3）・表・リストを保持。
- ナビゲーションやフッターなど定型領域を除去。

### 3. サイト構造解析
- `<a href>` タグから内部リンクを抽出。
- ノード＝ページ、エッジ＝リンクで `networkx` グラフを生成。  
- グラフのコミュニティ検出で関連ページを自動クラスタリング。

### 4. クラスタ命名
- 共通パス接頭辞 or TF-IDF上位語からクラスタラベルを生成。  
- スラッグは英小文字kebab-case形式で自動生成。

### 5. Markdown出力
- クラスタごとに統合ドキュメントを生成。
- 各ページに出典情報を付与：  
  ```
  > 出典: https://example.com/docs/intro （取得日時: 2025-11-06 JST）
  ```
- 元の階層構造をH見出しで再現。

### 6. Manifest出力
```json
{
  "pages": [{
    "page_id": "pg_001",
    "url": "https://example.com/faq",
    "file_path": "site_backup/faq.html",
    "title": "よくある質問",
    "cluster_id": "cl_support",
    "created_at": "2025-11-06T00:00:00+09:00"
  }],
  "clusters": [{
    "cluster_id": "cl_support",
    "label": "サポートFAQ",
    "slug": "support-faq",
    "page_ids": ["pg_001", "pg_002"]
  }]
}
```

---

## 使用技術
- **Pythonライブラリ**：  
  - `playwright`（DOMレンダリング・クリック展開）  
  - `beautifulsoup4` / `readability-lxml` / `trafilatura`（本文抽出）  
  - `networkx`（リンクグラフ構築・クラスタリング）  
  - `markdownify`（HTML→Markdown変換）  
  - `scikit-learn`（TF-IDFクラスタラベル補助）

---

## CLI設計（例）
```
python build_static_docs.py \
  --input ./site_backup \
  --out ./output \
  --graph \
  --workers 8 \
  --expand-texts "もっと見る,詳細,展開,Show more"
```

---

## 実行結果例
```
output/docs/support-faq.md

---
doc_id: doc_support-faq
cluster_label: サポートFAQ
cluster_slug: support-faq
source_urls:
  - https://example.com/faq/account
  - https://example.com/faq/payment
created_at: 2025-11-06T00:00:00+09:00
pages: [pg_account, pg_payment]
---

# サポートFAQ

## アカウントについて
> 出典: https://example.com/faq/account（2025-11-06 JST）

### パスワードを忘れた場合
...

## 支払いについて
> 出典: https://example.com/faq/payment（2025-11-06 JST）

### クレジットカードの変更
...
```

---

## 受け入れ基準
- 保存済みHTML群から**全ページのタイトル・見出し・本文が抽出**されている。  
- Playwright展開により、**クリック展開コンテンツも取得済み**である。  
- クラスタ単位でMarkdownが生成され、**出典URL・取得日時が正確に反映**されている。  
- `manifest.json` が全ページ分のメタ情報を保持している。  

---

## 今後の拡張（非スコープ）
- WARC形式の入力対応（Browsertrix連携）。  
- 差分ビルド（再取得最適化）。  
- クラスタ名の人手編集UI。  
- RAG前処理（チャンク化・埋め込み）への接続。
