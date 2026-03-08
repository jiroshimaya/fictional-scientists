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

## 開発

```bash
# フォーマット・型チェック・テストを一括実行
uv run task check

# テストのみ
uv run pytest tests
```

## ライセンス

MIT ライセンス。詳細は [LICENSE](LICENSE) をご覧ください。
