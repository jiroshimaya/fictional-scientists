"""
expanded CSV と names CSV をもとに架空科学者の詳細プロフィールと肖像画プロンプトを生成する。
名前は names CSV から取得し、それ以外の情報（生年没年、業績、研究内容等）を生成する。
"""

import argparse
import csv
import difflib
import json
import os
import random
import time
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

# ============================================================
# 設定
# ============================================================

MODEL = "gpt-4.1-mini"
INPUT_CSV = "data/attributes/fictional_scientist_quota_expanded_10000.csv"
NAMES_CSV = "data/names/fictional_scientist_names.csv"
OUTPUT_JSONL = "fictional_scientists.jsonl"
OUTPUT_PORTRAIT_JSONL = "fictional_scientists_portraits.jsonl"
MAX_ROWS_TO_GENERATE = 50
SUMMARY_SIMILARITY_THRESHOLD = 0.88

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


# ============================================================
# JSON Schema
# ============================================================

PROFILE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "生年": {"type": "integer"},
        "没年": {"type": ["integer", "null"]},
        "主な分野": {"type": "string"},
        "業績・受賞歴": {"type": "string"},
        "研究内容（要約）": {"type": "string"},
        "研究内容（詳細）": {"type": "string"},
    },
    "required": [
        "生年",
        "没年",
        "主な分野",
        "業績・受賞歴",
        "研究内容（要約）",
        "研究内容（詳細）",
    ],
}

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

PROFILE_SYSTEM_PROMPT = """
あなたは、科学史・科学社会史・学術文化に詳しい創作支援AIです。
大規模データセット用の架空科学者プロフィールを生成します。

重要:
- 実在人物を生成しない
- 実在人物の明白なもじりも避ける
- 時代・地域・分野に整合する人物にする
- 出力はJSONのみ
- 定型的な「天才」人物像を避け、研究対象・方法・制度的立場・評価のされ方に変化を持たせる
- 単発呼び出しなので「他サンプルとの完全な非重複」は要求しないが、既視感の強い業績・研究テーマの組み合わせは避ける
"""

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


def build_profile_user_prompt(
    name: str,
    era: str,
    gender: str,
    nationality: str,
    birth_year: int,
    field: str,
    recent_examples: List[Dict[str, str]],
) -> str:
    recent_block = ""
    if recent_examples:
        lines = []
        for ex in recent_examples[-20:]:
            lines.append(
                f"- 名前: {ex.get('名前', '?')} / 国籍: {ex.get('国籍', '?')} / 分野: {ex.get('主な分野', '?')} / 要約: {ex.get('研究内容（要約）', '?')[:80]}"
            )
        recent_block = "\n".join(lines)
    else:
        recent_block = "なし"

    return f"""
以下の名前と属性に基づいて、架空科学者のプロフィール（名前以外）を生成してください。

【名前（固定・変更不可）】
{name}

【入力属性】
- 時代区分: {era}
- 性別: {gender}
- 国籍: {nationality}
- 生年: {birth_year}
- 主な分野: {field}

【要件】
- 没年は自然な場合のみ設定し、存命なら null
- 研究内容（要約）は 50字以内（「他」などで省略可）
- 研究内容（詳細）は 350〜700字程度
- 詳細では、研究対象、方法、理論的視点または観測・実験手法、代表的成果、意義を書く
- 要約と詳細は言い換えだけにしない
- 業績・受賞歴は時代相応にする
- 研究内容は架空だが分野的に自然にする
- ありきたりな定型人物を避ける

【時代整合の例】
- 古代・中世では、近代的大学制度、ノーベル賞、量子論、半導体、加速器、コンピュータ計算などを出さない
- 1400–1799では、実験自然学、力学、光学、天文学、物質論、計測器具、学会、書簡ネットワークなどは可
- 1800–1899では、学会、観測所、実験室、学士院、分光、熱学、電磁気学などは可
- 1900–1949では、理論物理、原子論、量子論、初期宇宙論、核物理、精密実験などは可
- 1950年以降では、材料研究、凝縮系、プラズマ、宇宙観測、国際会議、計算機利用などを自然に使ってよい
- 2000年以降生まれの人物は若手として扱い、過剰な受賞歴は避ける

【最近生成したサンプル】
{recent_block}

【最近生成したサンプルに対する指示】
- これらと研究テーマ、業績表現が似すぎないようにする
- 同じ国籍・同じ分野でも研究対象や方法を少しずらす
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
- 名前: {profile["名前"]}
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
    temperature_note: Optional[str] = None,
) -> Dict[str, Any]:
    extra_instruction = ""
    if temperature_note:
        extra_instruction = f"\n\n補足: {temperature_note}"

    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt + extra_instruction},
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
# 重複チェック
# ============================================================


def normalize_text(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


def looks_duplicate(
    candidate: Dict[str, Any], existing: List[Dict[str, Any]]
) -> Tuple[bool, str]:
    cand_summary = candidate["研究内容（要約）"]
    for item in existing:
        if candidate.get("国籍") == item.get("国籍") and candidate.get(
            "主な分野"
        ) == item.get("主な分野"):
            summary_sim = similarity(cand_summary, item.get("研究内容（要約）", ""))
            if summary_sim >= SUMMARY_SIMILARITY_THRESHOLD:
                return (
                    True,
                    f"summary_too_similar:{item.get('名前', '?')}:{summary_sim:.3f}",
                )
    return False, ""


# ============================================================
# 生成ロジック
# ============================================================


def generate_one_profile(
    name: str,
    era: str,
    gender: str,
    nationality: str,
    birth_year: int,
    field: str,
    existing_profiles: List[Dict[str, Any]],
    max_attempts: int = 5,
) -> Dict[str, Any]:
    recent_examples = existing_profiles[-20:]
    last_error = None

    for attempt in range(1, max_attempts + 1):
        user_prompt = build_profile_user_prompt(
            name=name,
            era=era,
            gender=gender,
            nationality=nationality,
            birth_year=birth_year,
            field=field,
            recent_examples=recent_examples,
        )
        profile = create_structured_json(
            model=MODEL,
            system_prompt=PROFILE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            schema_name="scientist_profile",
            schema=PROFILE_SCHEMA,
            temperature_note=f"attempt={attempt}",
        )
        is_dup, reason = looks_duplicate(profile, existing_profiles)
        if not is_dup:
            return profile
        last_error = f"duplicate_rejected:{reason}"
        time.sleep(0.5)

    raise RuntimeError(
        f"Failed to generate non-duplicate profile after retries: {last_error}"
    )


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
# CSV / JSONL 読み書き
# ============================================================


def load_quota_rows(path: str) -> List[Dict[str, Any]]:
    """展開済み CSV を読み込む。"""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_names_by_id(path: str) -> Dict[str, Dict[str, str]]:
    """names CSV を id をキーとした辞書で読み込む。"""
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            return {r["id"]: r for r in csv.DictReader(f)}
    except FileNotFoundError:
        return {}


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
# メイン
# ============================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="expanded CSV + names CSV をもとにプロフィールを生成する"
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=MAX_ROWS_TO_GENERATE,
        help="処理する行数の上限 (デフォルト: %(default)s)",
    )
    parser.add_argument("--input", default=INPUT_CSV)
    parser.add_argument("--names", default=NAMES_CSV)
    parser.add_argument("--output", default=OUTPUT_JSONL)
    parser.add_argument("--output-portrait", default=OUTPUT_PORTRAIT_JSONL)
    args = parser.parse_args()

    quota_rows = load_quota_rows(args.input)
    names_by_id = load_names_by_id(args.names)
    existing_profiles = load_jsonl(args.output)
    generated_profiles: List[Dict[str, Any]] = list(existing_profiles)
    total_created = 0

    for row_idx, row in enumerate(quota_rows):
        if total_created >= args.max_rows:
            break

        scientist_id = row["id"]
        era = row["era_name"]
        gender = row["gender"]
        nationality = row["nationality"]
        birth_year_start = int(row["birth_year_start"])
        birth_year_end = int(row["birth_year_end"])
        field = row["field"]

        if is_id_already_generated(existing_profiles, scientist_id):
            print(f"[skip] {scientist_id}")
            continue

        name_record = names_by_id.get(scientist_id)
        if name_record is None:
            print(f"[skip] {scientist_id}: name not yet generated")
            continue

        name = name_record["名前"]
        birth_year = random.randint(birth_year_start, birth_year_end)
        name_fields = {
            k: name_record[k] for k in ["名前", "姓", "名", "ナマエ", "セイ", "メイ"]
        }

        try:
            profile = generate_one_profile(
                name=name,
                era=era,
                gender=gender,
                nationality=nationality,
                birth_year=birth_year,
                field=field,
                existing_profiles=generated_profiles,
            )
        except Exception as e:
            print(f"[profile_error] {scientist_id} err={e}")
            continue

        generated_profiles.append({**profile, "名前": name, "国籍": nationality})

        profile_record = {
            "id": scientist_id,
            "era": era,
            "gender": gender,
            "国籍": nationality,
            **name_fields,
            **profile,
        }
        append_jsonl(args.output, profile_record)

        combined_for_portrait = {
            **profile,
            "名前": name,
            "国籍": nationality,
        }

        try:
            portrait = generate_one_portrait_prompt(
                profile=combined_for_portrait,
                era=era,
                gender=gender,
            )
        except Exception as e:
            print(f"[portrait_error] name={name} err={e}")
            portrait = {"portrait_prompt": "", "negative_prompt": "", "style_note": ""}

        portrait_record = {
            "id": scientist_id,
            "名前": name,
            "era": era,
            "gender": gender,
            "nationality": nationality,
            "field": field,
            **portrait,
        }
        append_jsonl(args.output_portrait, portrait_record)

        total_created += 1
        print(
            f"[ok] {total_created} ({scientist_id}): {name} / {nationality} / {field}"
        )
        time.sleep(0.3)

    print(f"done: generated={total_created}")


if __name__ == "__main__":
    main()
