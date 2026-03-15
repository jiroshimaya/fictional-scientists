# Fictional Scientists

架空の科学者データセットを生成するツールです。OpenAI API を使用して、時代・国籍・分野ごとに多様な架空科学者の名前、詳細プロフィール、肖像画プロンプト、および肖像画画像を生成します。

## 概要

以下のパイプラインでデータを生成します。

```
quota.csv
    ↓ generate_name.py
names.csv
    ↓ generate_profile.py
profiles.jsonl
    ↓ generate_portrait_prompt.py
portrait_prompts.jsonl
    ↓ generate_images.py
portraits/{id}.png
```

`--dir` でディレクトリを指定した場合、各スクリプトは同一ディレクトリ内の以下のファイルを入出力します。

```
$DIR/
├── quota.csv                # 入力（必須）
├── names.csv                # generate_name.py の出力
├── profiles.jsonl           # generate_profile.py の出力
├── portrait_prompts.jsonl   # generate_portrait_prompt.py の出力
└── portraits/
    └── {id}.png             # generate_images.py の出力
```

## セットアップ

```bash
sh scripts/setup.sh
```

環境変数に OpenAI API キーを設定してください。

```bash
export OPENAI_API_KEY="your-api-key"
```

## 使い方

### 1. クォータCSVの展開

`data/attributes/fictional_scientist_quota_master_10000.csv` の各行を `count` の数だけ複製し、複合 id を付与した展開済み CSV を生成します。

```bash
uv run python expand_quota.py
# オプション指定の場合
uv run python expand_quota.py --input <入力CSV> --output <出力CSV>
```

### 2. 名前の生成

入力: `quota.csv` → 出力: `names.csv`

`quota.csv` をもとに架空科学者の名前（姓・名・読み仮名）を生成します。

```bash
DIR=data/sample/two uv run task generate
# 個別実行の場合
uv run python generate_name.py --dir $DIR
# 件数上限を変更する場合
uv run python generate_name.py --dir $DIR --max-rows 100
```

### 3. プロフィールの生成

入力: `quota.csv` → 出力: `profiles.jsonl`

`quota.csv` をもとに、各科学者の詳細プロフィールを生成します。

```bash
uv run python generate_profile.py --dir $DIR
# 件数上限を変更する場合
uv run python generate_profile.py --dir $DIR --max-rows 100
```

### 4. 肖像画プロンプトの生成

入力: `profiles.jsonl` → 出力: `portrait_prompts.jsonl`

`profiles.jsonl` をもとに、肖像画生成用のプロンプトを生成します。

```bash
uv run python generate_portrait_prompt.py --dir $DIR
```

### 5. 肖像画の生成

入力: `portrait_prompts.jsonl` → 出力: `portraits/{id}.png`

`portrait_prompts.jsonl` をもとに `gpt-image-1` で画像を生成し、`portraits/` に PNG として保存します。

```bash
uv run python generate_images.py --dir $DIR
```

### 6. Wikipedia から科学者一覧を取得

既存の `names.csv` は架空科学者生成用です。Wikipedia 上の実在科学者を一括取得したい場合は、`create_scientists_csv.py` でカテゴリから `scientists.csv` を直接生成します。

既定では `Category:科学者` だけでなく、`Category:自然哲学者`、`Category:ノーベル賞受賞者`、`Category:医学者`、`Category:地球科学者`、`Category:コンピュータ科学者` などもまとめて起点にします。アリストテレスのような古い自然哲学者から、ノーベル賞受賞者や近現代の周辺科学分野まで拾いやすくするためです。既定の再帰深さも 3 にして、サブカテゴリをもう一段深く辿ります。

```bash
uv run python create_scientists_csv.py --dir $DIR

# 例: 英語版Wikipediaの広域カテゴリ群を使って取得
uv run python create_scientists_csv.py \
  --output data/wikipedia/scientists_en.csv \
  --language en

# 例: 特定カテゴリだけに絞る場合は --category を複数指定できる
uv run python create_scientists_csv.py \
  --output data/wikipedia/physicists.csv \
  --language en \
  --category Category:Physicists \
  --category Category:Natural\ philosophers \
  --max-depth 2

# 例: 分類メモ推定を省略して高速に件数だけ増やす
uv run python create_scientists_csv.py \
  --output data/wikipedia/scientists_ja.csv \
  --language ja \
  --max-members 1000 \
  --skip-memo-inference
```

出力には `id`, `名前`, `wikipedia_title`, `url`, `language`, `source_category`, `pageid` に加えて、`era_name`, `gender`, `nationality_region`, `nationality` を含めます。既定ではこれらを Wikipedia のページカテゴリから**初期推定値として自動で埋め**、手で修正した値は再生成しても保持されます。高速に件数を増やしたい場合は `--skip-memo-inference` を使うと、この推定を省略して一覧取得を優先できます。

### 7. Wikipedia から顔画像をダウンロード

入力: `scientists.csv` (`id`, `名前`, 任意で `wikipedia_title`) → 出力: `wikipedia_faces/{id}.jpg` など

Wikipedia の page summary API を使って代表画像を取得します。`wikipedia_title` があればそれを優先し、なければ `名前` でページを引きます。既定では元言語ページで画像が見つからない場合に英語版へフォールバックします。

```bash
# 既定では $DIR/scientists.csv を読み、$DIR/wikipedia_faces/ に保存
uv run python download_wikipedia_faces.py --dir $DIR

# 任意CSVを指定する場合
uv run python download_wikipedia_faces.py \
  --input path/to/scientists.csv \
  --output-dir path/to/wikipedia_faces \
  --language en

# 英語版以外も試したい場合
uv run python download_wikipedia_faces.py \
  --input path/to/scientists.csv \
  --output-dir path/to/wikipedia_faces \
  --language ja \
  --fallback-languages en,de,fr
```

### 8. 日本語 Wikipedia / Wikidata / Commons から科学者画像を一括収集

入力: 日本語 Wikipedia のカテゴリ木 → 出力: `scientist_faces/` と `scientist_faces/scientist_images.csv`

`download_scientists.py` は `Category:科学者` を起点に記事を再帰収集し、`page_image_free` と Wikidata の `P18` を見ながら Commons 画像を保存します。記事タイトル一覧は `titles_ja_scientists.txt` にキャッシュし、再実行時は既存キャッシュと CSV を使って続きから進められます。

```bash
# 既定では scientist_faces/ 配下に画像・CSV・タイトルキャッシュを保存
uv run python download_scientists.py

# 出力先を変える場合
uv run python download_scientists.py \
  --output-dir data/wikipedia/scientist_faces

# タイトルキャッシュを捨ててカテゴリ木を再取得する場合
uv run python download_scientists.py \
  --output-dir data/wikipedia/scientist_faces \
  --refresh-cache
```

### 9. 顔埋め込みベクトルで肖像画像の多様性を評価

入力: `portraits/` または `wikipedia_faces/` を含むディレクトリ、もしくは画像ディレクトリそのもの → 出力: `portrait_embedding_evaluation.csv`

InsightFace の顔埋め込みモデルを使って、画像ごとの顔埋め込みベクトル、最近傍距離、バッチ全体の平均ペアワイズコサイン距離を CSV に書き出します。

- `batch_diversity_score` は `1 - 平均コサイン類似度` です
- `nearest_neighbor_distance` で「その画像が最も似ている相手」との距離を確認できます
- 顔が検出できなかった画像は `status=error` と `error` 列に理由を書き出します

```bash
# 依存関係を入れる
uv sync

# $DIR/portraits/ を自動検出して評価する
uv run python evaluate_portraits_embeddings.py --dir $DIR

# portraits/ ディレクトリを直接渡すこともできる
uv run python evaluate_portraits_embeddings.py \
  --dir data/sample/two_similar/portraits

# Wikipedia 顔画像ディレクトリを明示指定する例
uv run python evaluate_portraits_embeddings.py \
  --dir data/sample/two_different \
  --image-dir data/sample/two_different/wikipedia_faces \
  --batch-name two_different
```

出力CSVには `embedding_json`、`nearest_neighbor_distance`、`batch_diversity_score`、`embedding_model` などが含まれるので、`two_similar` / `two_different` や `ten_similar_*` / `ten_different_*` の比較に使えます。
## データ形式

### プロフィール JSONL（`profiles.jsonl`）

```json
{
  "id": "近代後期__実験物理__日本__0001",
  "era": "近代後期",
  "gender": "男性",
  "国籍": "日本",
  "主な分野": "実験物理",
  "生年": 1878,
  "没年": 1943,
  "研究内容（要約）": "..."
}
```

### 肖像画プロンプト JSONL（`portrait_prompts.jsonl`）

```json
{
  "id": "近代後期__実験物理__日本__0001",
  "era": "近代後期",
  "gender": "男性",
  "nationality": "日本",
  "field": "実験物理",
  "portrait_prompt": "...",
  "negative_prompt": "...",
  "style_note": "..."
}
```

### 名前 CSV（`names.csv`）

```
id,名前,姓,名,ナマエ,セイ,メイ
近代後期__実験物理__日本__0001,松田 清志,松田,清志,マツダ キヨシ,マツダ,キヨシ
```

### Wikipedia 入力 CSV（`scientists.csv`）

```csv
id,名前,wikipedia_title,url,language,source_category,pageid
id,名前,era_name,gender,nationality_region,nationality,wikipedia_title,url,language,source_category,pageid
wikipedia-ja-736,アルベルト・アインシュタイン,近代後期,男性,西欧,ドイツ,アルベルト・アインシュタイン,https://ja.wikipedia.org/wiki/%E3%82%A2%E3%83%AB%E3%83%99%E3%83%AB%E3%83%88%E3%83%BB%E3%82%A2%E3%82%A4%E3%83%B3%E3%82%B7%E3%83%A5%E3%82%BF%E3%82%A4%E3%83%B3,ja,Category:科学者,736
```

## 開発

```bash
# フォーマット・型チェック・テストを一括実行
uv run task check

# テストのみ
uv run pytest tests
```

## ライセンス

MIT ライセンス。詳細は [LICENSE](LICENSE) をご覧ください。
