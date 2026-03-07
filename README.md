# Fictional Scientists

架空の科学者データセットを生成するツールです。OpenAI API を使用して、時代・国籍・分野ごとに多様な架空科学者の名前、詳細プロフィール、肖像画プロンプト、および肖像画画像を生成します。

## 概要

以下のパイプラインでデータを生成します。

```
クォータマスターCSV
    ↓ expand_quota.py
展開済みCSV（id付き）
    ↓ generate_name.py
名前CSV
    ↓ generate_profile.py
プロフィールJSONL + 肖像画プロンプトJSONL
    ↓ generate_images.py
肖像画PNG（data/portraits/）
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

展開済み CSV をもとに架空科学者の名前（姓・名・読み仮名）を生成します。

```bash
uv run python generate_name.py
# 件数上限を変更する場合
uv run python generate_name.py --max-rows 100
```

### 3. プロフィールの生成

名前 CSV と展開済み CSV をもとに、各科学者の詳細プロフィールと肖像画プロンプトを生成します。

```bash
uv run python generate_profile.py
# 件数上限を変更する場合
uv run python generate_profile.py --max-rows 100
```

出力ファイル:
- `fictional_scientists.jsonl` — プロフィール（生年・没年・分野・業績・研究内容など）
- `fictional_scientists_portraits.jsonl` — 肖像画生成用プロンプト

### 4. 肖像画の生成

肖像画プロンプト JSONL をもとに `gpt-image-1` で画像を生成し、`data/portraits/` に PNG として保存します。

```bash
uv run python generate_images.py
```

## データ形式

### プロフィール JSONL（`fictional_scientists.jsonl`）

```json
{
  "id": "近代__物理学__日本__0001",
  "名前": "山田 太郎",
  "生年": 1872,
  "没年": 1941,
  "主な分野": "量子力学",
  "業績・受賞歴": "...",
  "研究内容（要約）": "...",
  "研究内容（詳細）": "..."
}
```

### 肖像画プロンプト JSONL（`fictional_scientists_portraits.jsonl`）

```json
{
  "id": "近代__物理学__日本__0001",
  "portrait_prompt": "...",
  "negative_prompt": "...",
  "style_note": "..."
}
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
