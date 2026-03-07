import os
import csv
import json
import time
import random
import pathlib
import difflib
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

# ============================================================
# 設定
# ============================================================

MODEL_TEXT = "gpt-5"
MODEL_TEXT_FAST = "gpt-5-mini"   # 軽量側で回したいとき用
INPUT_CSV = "data/attributes/fictional_scientist_quota_master_10000.csv"
OUTPUT_JSONL = "fictional_scientists.jsonl"
OUTPUT_PORTRAIT_JSONL = "fictional_scientists_portraits.jsonl"

# まずは少数で試す
MAX_ROWS_TO_GENERATE = 50

# 1 quota row から何人作るか。最初は小さめ推奨
PER_ROW_LIMIT = 3

# 重複っぽいと判定する閾値
NAME_SIMILARITY_THRESHOLD = 0.90
SUMMARY_SIMILARITY_THRESHOLD = 0.88

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


# ============================================================
# JSON Schema
# Structured Outputs 用
# ============================================================

PROFILE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "名前": {"type": "string"},
        "姓": {"type": "string"},
        "名": {"type": "string"},
        "ナマエ": {"type": "string"},
        "セイ": {"type": "string"},
        "メイ": {"type": "string"},
        "国籍": {"type": "string"},
        "生年": {"type": "integer"},
        "没年": {"type": ["integer", "null"]},
        "主な分野": {"type": "string"},
        "業績・受賞歴": {"type": "string"},
        "研究内容（要約）": {"type": "string"},
        "研究内容（詳細）": {"type": "string"},
    },
    "required": [
        "名前",
        "姓",
        "名",
        "ナマエ",
        "セイ",
        "メイ",
        "国籍",
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
- 単発呼び出しなので「他サンプルとの完全な非重複」は要求しないが、既視感の強い名前・業績・研究テーマの組み合わせは避ける
"""

PORTRAIT_SYSTEM_PROMPT = """
あなたは画像生成用プロンプト設計者です。
架空科学者プロフィールから、画像生成AI向けの肖像画プロンプトを作成します。

重要:
- 実在人物に似せない
- 時代・地域・分野に合う服装、背景、小物、画風にする
- 背景の情報量は控えめ
- 一人だけを描く
- 文字、署名、ロゴ、透かしを入れない
- 手や顔の破綻を避ける
- 出力はJSONのみ
"""


def build_profile_user_prompt(
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
                f"- 名前: {ex['名前']} / 国籍: {ex['国籍']} / 分野: {ex['主な分野']} / 要約: {ex['研究内容（要約）'][:80]}"
            )
        recent_block = "\n".join(lines)
    else:
        recent_block = "なし"

    return f"""
以下の属性に基づいて、実在しない架空の科学者を1名生成してください。

【入力】
- 時代区分: {era}
- 性別: {gender}
- 国籍: {nationality}
- 生年: {birth_year}
- 主な分野: {field}

【要件】
- 名前は国籍・時代に自然に合うものにする
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
- これらと名前の音、研究テーマ、業績表現が似すぎないようにする
- 完全一致はもちろん避ける
- 同じ国籍・同じ分野でも研究対象や方法を少しずらす
"""


def build_portrait_user_prompt(profile: Dict[str, Any], era: str, gender: str) -> str:
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

【要件】
- 実在人物に似せない
- 顔立ちは自然で知的に見えるようにする
- 過度な美化、英雄化、漫画化、ファンタジー化を避ける
- 時代、地域、学術的背景に合う服装・髪型・背景・小物を選ぶ
- 分野表現は背景や小物でほのめかす程度にする
- 文字、署名、ロゴ、透かし、額縁内の文章を入れない
- 手、顔、目、指の破綻を避ける指示を入れる
- 一人だけを描く
- 胸像、半身像、上半身ポートレートを基本にする
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
    """
    Structured Outputs で JSON を返す。
    Responses API は text/JSON 出力に対応し、Structured Outputs は JSON mode より
    スキーマ準拠が強い。 [oai_citation:1‡OpenAI Developers](https://developers.openai.com/api/reference/resources/responses/methods/create)
    """
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

    # Structured Outputs を使っても、受け取り側で parse/validate するのが安全
    # ここでは output_text を JSON loads
    return json.loads(resp.output_text)


# ============================================================
# 重複チェック
# ============================================================

def normalize_text(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


def looks_duplicate(candidate: Dict[str, Any], existing: List[Dict[str, Any]]) -> Tuple[bool, str]:
    cand_name = candidate["名前"]
    cand_summary = candidate["研究内容（要約）"]

    for item in existing:
        name_sim = similarity(cand_name, item["名前"])
        if name_sim >= NAME_SIMILARITY_THRESHOLD:
            return True, f"name_too_similar:{item['名前']}:{name_sim:.3f}"

        # 同国籍・同分野のときは要約類似を厳しめに見る
        if (
            candidate["国籍"] == item["国籍"]
            and candidate["主な分野"] == item["主な分野"]
        ):
            summary_sim = similarity(cand_summary, item["研究内容（要約）"])
            if summary_sim >= SUMMARY_SIMILARITY_THRESHOLD:
                return True, f"summary_too_similar:{item['名前']}:{summary_sim:.3f}"

    return False, ""


# ============================================================
# 生成ロジック
# ============================================================

def generate_one_profile(
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
            era=era,
            gender=gender,
            nationality=nationality,
            birth_year=birth_year,
            field=field,
            recent_examples=recent_examples,
        )

        profile = create_structured_json(
            model=MODEL_TEXT,
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

    raise RuntimeError(f"Failed to generate non-duplicate profile after retries: {last_error}")


def generate_one_portrait_prompt(
    profile: Dict[str, Any],
    era: str,
    gender: str,
) -> Dict[str, Any]:
    user_prompt = build_portrait_user_prompt(profile=profile, era=era, gender=gender)

    return create_structured_json(
        model=MODEL_TEXT_FAST,
        system_prompt=PORTRAIT_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema_name="portrait_prompt",
        schema=PORTRAIT_SCHEMA,
    )


# ============================================================
# CSV 読み込み
# ============================================================

def load_quota_rows(path: str) -> List[Dict[str, Any]]:
    """
    ここでは最低限、以下の列がある想定:
    - era
    - gender
    - nationality
    - field
    - count

    birth_year は後で era からサンプリングしてもよい。
    """
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def sample_birth_year_from_era(era: str) -> int:
    """
    例:
      '1900–1949' のような表記を想定
      '紀元前400–紀元前1' のようなケースは必要に応じて拡張
    """
    era = era.strip()

    if "紀元前" in era:
        # 簡易実装。必要ならもっと丁寧にパース
        if era == "紀元前400–紀元前1":
            return -random.randint(1, 400)

    era = era.replace("–", "-").replace("—", "-")
    parts = era.split("-")
    if len(parts) == 2:
        start = int(parts[0])
        end = int(parts[1])
        return random.randint(start, end)

    raise ValueError(f"Unsupported era format: {era}")


# ============================================================
# 保存
# ============================================================

def append_jsonl(path: str, record: Dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ============================================================
# メイン
# ============================================================

def main() -> None:
    quota_rows = load_quota_rows(INPUT_CSV)

    generated_profiles: List[Dict[str, Any]] = []
    total_created = 0

    pathlib.Path(OUTPUT_JSONL).unlink(missing_ok=True)
    pathlib.Path(OUTPUT_PORTRAIT_JSONL).unlink(missing_ok=True)

    for row_idx, row in enumerate(quota_rows):
        if row_idx >= MAX_ROWS_TO_GENERATE:
            break

        # CSV 側の列名に合わせてここは調整してください
        era = row.get("era_name")
        birth_year_start = row.get("birth_year_start")
        birth_year_end = row.get("birth_year_end")
        gender = row.get("gender")
        nationality = row.get("nationality")
        field = row.get("field")
        count_str = row.get("count") or "1"

        if not all([era, gender, nationality, field]):
            print(f"[skip] missing required columns: row_idx={row_idx}")
            continue

        try:
            count = int(count_str)
        except ValueError:
            count = 1

        n_to_generate = min(count, PER_ROW_LIMIT)

        for _ in range(n_to_generate):
            try:
                birth_year = random.randint(int(birth_year_start), int(birth_year_end))
            except (TypeError, ValueError):
                birth_year = sample_birth_year_from_era(era)

            try:
                profile = generate_one_profile(
                    era=era,
                    gender=gender,
                    nationality=nationality,
                    birth_year=birth_year,
                    field=field,
                    existing_profiles=generated_profiles,
                )
            except Exception as e:
                print(f"[profile_error] row_idx={row_idx} err={e}")
                continue

            generated_profiles.append(profile)

            profile_record = {
                "era": era,
                "gender": gender,
                **profile,
            }
            append_jsonl(OUTPUT_JSONL, profile_record)

            try:
                portrait = generate_one_portrait_prompt(
                    profile=profile,
                    era=era,
                    gender=gender,
                )
            except Exception as e:
                print(f"[portrait_error] name={profile['名前']} err={e}")
                portrait = {
                    "portrait_prompt": "",
                    "negative_prompt": "",
                    "style_note": "",
                }

            portrait_record = {
                "名前": profile["名前"],
                "era": era,
                "gender": gender,
                "nationality": profile["国籍"],
                "field": profile["主な分野"],
                **portrait,
            }
            append_jsonl(OUTPUT_PORTRAIT_JSONL, portrait_record)

            total_created += 1
            print(f"[ok] {total_created}: {profile['名前']} / {profile['国籍']} / {profile['主な分野']}")

            # レート制御は適宜
            time.sleep(0.3)

    print(f"done: generated={total_created}")


if __name__ == "__main__":
    main()