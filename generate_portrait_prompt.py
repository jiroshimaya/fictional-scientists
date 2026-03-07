"""
profiles JSONL をもとに架空科学者の肖像画プロンプトを生成する。
"""

import argparse
import json
import os
import time
from typing import Any, Dict, List

from openai import OpenAI

# ============================================================
# 設定
# ============================================================

MODEL = "gpt-4.1-mini"
INPUT_PROFILES = "data/profiles/fictional_scientist_profiles.jsonl"
OUTPUT_PORTRAIT_JSONL = "fictional_scientists_portraits.jsonl"
MAX_ROWS_TO_GENERATE = 50

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


# ============================================================
# JSON Schema
# ============================================================

PORTRAIT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "portrait_prompt": {"type": "string"},
        "negative_prompt": {"type": "string"},
        "style_note": {"type": "string"},
    },
    "required": ["portrait_prompt", "negative_prompt", "style_note"],
}


# ============================================================
# プロンプト
# ============================================================

PORTRAIT_SYSTEM_PROMPT = """
あなたは画像生成用プロンプト設計者です。
架空科学者プロフィールから、画像生成AI向けの肖像画プロンプトを作成します。

重要:
- 実在人物に似せない
- 時代・地域・分野に合う服装、背景、小物、画風にする
- 歴史的に実在しうるポートレートの形式（石彫、油彩、写真など）を選ぶ
- 背景の情報量は控えめ
- 一人だけを描く
- 文字、署名、ロゴ、透かしを入れない
- 手や顔の破綻を避ける
- 出力はJSONのみ
"""

_PORTRAIT_ERA_CONTEXTS: Dict[str, Dict[str, str]] = {
    "古代前期": {
        "medium": (
            "Choose one of these historically appropriate formats: "
            "carved stone relief (fragmentary), marble sculpture bust (weathered), "
            "terracotta figurine, fresco wall painting fragment (damaged), "
            "mosaic portrait (partially restored)"
        ),
        "preservation": (
            "heavily weathered, partially damaged, some features worn away, "
            "fragmentary or reconstructed, ancient stone patina"
        ),
        "pose": (
            "frontal or profile carved in stone, seated formal pose, "
            "standing ceremonial pose, or partial bust fragment"
        ),
    },
    "古代後期": {
        "medium": (
            "Choose one of: marble bust portrait, mosaic portrait, "
            "encaustic wax panel painting (Fayum portrait style), fresco"
        ),
        "preservation": "weathered, some color faded or lost, aged patina, minor damage",
        "pose": "frontal facing, three-quarter view, or formal seated",
    },
    "中世前期": {
        "medium": (
            "Choose one of: Byzantine icon (gold background, flat stylized style), "
            "illuminated manuscript miniature, fresco"
        ),
        "preservation": "faded colors, slightly damaged edges, aged parchment or plaster",
        "pose": "frontal formal pose, stylized, seated in scholarly or religious setting",
    },
    "中世後期": {
        "medium": (
            "Choose one of: illuminated manuscript illustration, "
            "stone effigy or tomb sculpture, fresco, early panel painting"
        ),
        "preservation": "aged, slightly faded, minor damage, medieval character",
        "pose": (
            "semi-frontal or three-quarter, seated writing or standing, "
            "formal medieval pose"
        ),
    },
    "ルネサンス・初期近世": {
        "medium": (
            "Choose one of: oil painting on panel or canvas, "
            "engraving or woodcut print, tempera painting"
        ),
        "preservation": (
            "aged canvas or paper with slight yellowing, craquelure, "
            "well-preserved for its era"
        ),
        "pose": (
            "three-quarter view, profile, half-length or full-length, "
            "seated or standing with Renaissance-era setting"
        ),
    },
    "近世前期": {
        "medium": (
            "Choose one of: oil portrait on canvas, etching or mezzotint print, "
            "pastel drawing"
        ),
        "preservation": "aged canvas or paper, slight darkening of varnish, well-preserved",
        "pose": (
            "three-quarter view, seated at desk or standing, "
            "formal Baroque-style pose with objects or books"
        ),
    },
    "近世後期": {
        "medium": "Choose one of: oil portrait, pastel portrait, engraving, chalk drawing",
        "preservation": "aged but well-preserved, slight yellowing, 18th century character",
        "pose": (
            "three-quarter view, seated formal pose, half-length, "
            "with scientific instruments or books"
        ),
    },
    "近代前期": {
        "medium": (
            "Choose one of: oil portrait, watercolor portrait, lithograph, "
            "early daguerreotype (only if depicting late 1840s subject)"
        ),
        "preservation": "well-preserved, slight aging, 19th century style",
        "pose": "formal seated or standing, three-quarter view, half-length portrait",
    },
    "近代後期": {
        "medium": (
            "photographic portrait — albumen print, silver gelatin print, "
            "or cabinet card photograph"
        ),
        "preservation": (
            "slightly yellowed or faded photograph, vintage silver tones, well-preserved"
        ),
        "pose": (
            "formal seated (common for Victorian/Meiji era photography), "
            "three-quarter view, standing in studio setting, "
            "or with laboratory equipment"
        ),
    },
    "現代前期": {
        "medium": "black-and-white photograph",
        "preservation": "well-preserved, classic monochrome",
        "pose": (
            "formal or semi-formal, three-quarter view, seated or standing, "
            "office / laboratory / outdoor setting"
        ),
    },
    "現代中期": {
        "medium": "color or black-and-white photograph",
        "preservation": "well-preserved",
        "pose": (
            "varied: formal, outdoor, laboratory, conference, "
            "three-quarter or frontal"
        ),
    },
    "現代後期": {
        "medium": "color photograph or digital photograph",
        "preservation": "well-preserved, modern",
        "pose": (
            "varied: professional, casual, outdoor, laboratory setting, "
            "three-quarter or frontal"
        ),
    },
    "現代最年少": {
        "medium": "digital photograph",
        "preservation": "modern, crisp",
        "pose": (
            "varied: professional headshot, casual, laboratory, "
            "three-quarter or frontal"
        ),
    },
}


def _get_portrait_era_context(era_name: str) -> Dict[str, str]:
    """時代名に基づいてポートレートの媒体・保存状態・ポーズ情報を返す。"""
    return _PORTRAIT_ERA_CONTEXTS.get(
        era_name,
        {
            "medium": "oil portrait or photograph depending on era",
            "preservation": "aged or well-preserved",
            "pose": "three-quarter view, seated or standing",
        },
    )


def build_portrait_user_prompt(profile: Dict[str, Any], era: str, gender: str) -> str:
    ctx = _get_portrait_era_context(era)
    return f"""
以下の架空科学者プロフィールをもとに、画像生成AI向けの肖像画プロンプトを作成してください。

【入力プロフィール】
- 性別: {gender}
- 国籍: {profile["国籍"]}
- 生年: {profile["生年"]}
- 没年: {profile["没年"]}
- 時代区分: {era}
- 主な分野: {profile["主な分野"]}
- 研究内容（要約）: {profile["研究内容（要約）"]}

【ポートレートの記録形式】
この時代に実在しうる歴史的な媒体・記録形式（どの程度の資料が残っているかのリアリティ）:
{ctx["medium"]}

【保存状態】
{ctx["preservation"]}

【ポーズの候補】
{ctx["pose"]}

【要件】
- 実在人物に似せない
- 顔立ちは自然で知的に見えるようにする
- 過度な美化、英雄化、漫画化、ファンタジー化を避ける
- 時代、地域、学術的背景に合う服装・髪型・背景・小物を選ぶ
- 分野表現は背景や小物でほのめかす程度にする
- 文字、署名、ロゴ、透かし、額縁内の文章を入れない
- 手、顔、目、指の破綻を避ける指示を入れる
- 一人だけを描く
- 上記のポーズ候補から時代・媒体に合うものを選び、自然なバリエーションを持たせる
"""


# ============================================================
# OpenAI Responses API 呼び出し
# ============================================================


def create_structured_json(
    model: str,
    system_prompt: str,
    user_prompt: str,
    schema_name: str,
    schema: Dict[str, Any],
) -> Dict[str, Any]:
    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": schema,
                "strict": True,
            }
        },
    )
    return json.loads(resp.output_text)


# ============================================================
# JSONL 読み書き
# ============================================================


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    """JSONL ファイルを読み込む。ファイルが存在しない場合は空リストを返す。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return []


def is_id_already_generated(records: List[Dict[str, Any]], scientist_id: str) -> bool:
    """指定した id のレコードが既に生成済みかどうかを返す。"""
    return any(r.get("id") == scientist_id for r in records)


def append_jsonl(path: str, record: Dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ============================================================
# 生成ロジック
# ============================================================


def generate_one_portrait_prompt(
    profile: Dict[str, Any],
    era: str,
    gender: str,
) -> Dict[str, Any]:
    user_prompt = build_portrait_user_prompt(profile=profile, era=era, gender=gender)
    return create_structured_json(
        model=MODEL,
        system_prompt=PORTRAIT_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema_name="portrait_prompt",
        schema=PORTRAIT_SCHEMA,
    )


# ============================================================
# メイン
# ============================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="profiles JSONL をもとに肖像画プロンプトを生成する"
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=MAX_ROWS_TO_GENERATE,
        help="処理する行数の上限 (デフォルト: %(default)s)",
    )
    parser.add_argument("--input", default=INPUT_PROFILES)
    parser.add_argument("--output", default=OUTPUT_PORTRAIT_JSONL)
    args = parser.parse_args()

    profile_records = load_jsonl(args.input)
    existing_portraits = load_jsonl(args.output)
    total_created = 0

    for record in profile_records:
        if total_created >= args.max_rows:
            break

        scientist_id = record["id"]
        era = record["era"]
        gender = record["gender"]

        if is_id_already_generated(existing_portraits, scientist_id):
            print(f"[skip] {scientist_id}")
            continue

        try:
            portrait = generate_one_portrait_prompt(
                profile=record,
                era=era,
                gender=gender,
            )
        except Exception as e:
            print(f"[portrait_error] {scientist_id} err={e}")
            portrait = {"portrait_prompt": "", "negative_prompt": "", "style_note": ""}

        portrait_record = {
            "id": scientist_id,
            "era": era,
            "gender": gender,
            "nationality": record.get("国籍", ""),
            "field": record.get("主な分野", ""),
            **portrait,
        }
        append_jsonl(args.output, portrait_record)

        total_created += 1
        print(f"[ok] {total_created} ({scientist_id})")
        time.sleep(0.3)

    print(f"done: generated={total_created}")


if __name__ == "__main__":
    main()
