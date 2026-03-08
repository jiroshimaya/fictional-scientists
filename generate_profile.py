"""
expanded CSV をもとに架空科学者の詳細プロフィールを生成する。
"""

import argparse
import csv
import difflib
import json
import os
import pathlib
import random
import time
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

# ============================================================
# 設定
# ============================================================

MODEL = "gpt-4.1-mini"
INPUT_CSV = "data/attributes/fictional_scientist_quota_expanded_10000.csv"
OUTPUT_JSONL = "data/profiles/fictional_scientist_profiles.jsonl"
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
        "研究内容（要約）": {"type": "string"},
    },
    "required": [
        "生年",
        "没年",
        "研究内容（要約）",
    ],
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
- 単発呼び出しなので「他サンプルとの完全な非重複」は要求しないが、既視感の強い研究テーマの組み合わせは避ける
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
                f"- 国籍: {ex.get('国籍', '?')} / 分野: {ex.get('主な分野', '?')} / 要約: {ex.get('研究内容（要約）', '?')[:80]}"
            )
        recent_block = "\n".join(lines)
    else:
        recent_block = "なし"

    return f"""
以下の属性に基づいて、架空科学者のプロフィールを生成してください。

【入力属性】
- 時代区分: {era}
- 性別: {gender}
- 国籍: {nationality}
- 生年: {birth_year}
- 主な分野: {field}

【要件】
- 没年は自然な場合のみ設定し、存命なら null
- 研究内容（要約）は 50字以内（「他」などで省略可）
- 研究内容は架空だが分野的に自然にする
- ありきたりな定型人物を避ける

【時代整合の例】
- 古代・中世では、近代的大学制度、ノーベル賞、量子論、半導体、加速器、コンピュータ計算などを出さない
- 1400–1799では、実験自然学、力学、光学、天文学、物質論、計測器具、学会、書簡ネットワークなどは可
- 1800–1899では、学会、観測所、実験室、学士院、分光、熱学、電磁気学などは可
- 1900–1949では、理論物理、原子論、量子論、初期宇宙論、核物理、精密実験などは可
- 1950年以降では、材料研究、凝縮系、プラズマ、宇宙観測、国際会議、計算機利用などを自然に使ってよい
- 2000年以降生まれの人物は若手として扱う

【最近生成したサンプル】
{recent_block}

【最近生成したサンプルに対する指示】
- これらと研究テーマが似すぎないようにする
- 同じ国籍・同じ分野でも研究対象や方法を少しずらす
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
    candidate: Dict[str, Any],
    existing: List[Dict[str, Any]],
    nationality: str,
    field: str,
) -> Tuple[bool, str]:
    cand_summary = candidate["研究内容（要約）"]
    for item in existing:
        if nationality == item.get("国籍") and field == item.get("主な分野"):
            summary_sim = similarity(cand_summary, item.get("研究内容（要約）", ""))
            if summary_sim >= SUMMARY_SIMILARITY_THRESHOLD:
                return (
                    True,
                    f"summary_too_similar:{item.get('id', '?')}:{summary_sim:.3f}",
                )
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
            model=MODEL,
            system_prompt=PROFILE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            schema_name="scientist_profile",
            schema=PROFILE_SCHEMA,
            temperature_note=f"attempt={attempt}",
        )
        is_dup, reason = looks_duplicate(
            profile, existing_profiles, nationality=nationality, field=field
        )
        if not is_dup:
            return profile
        last_error = f"duplicate_rejected:{reason}"
        time.sleep(0.5)

    raise RuntimeError(
        f"Failed to generate non-duplicate profile after retries: {last_error}"
    )


# ============================================================
# CSV / JSONL 読み書き
# ============================================================


def load_quota_rows(path: str) -> List[Dict[str, Any]]:
    """展開済み CSV を読み込む。"""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


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


def find_expanded_csv_in_dir(dir_path: str) -> str:
    """ディレクトリ内の fictional_scientist_quota_expanded_*.csv を探す。"""
    candidates = list(
        pathlib.Path(dir_path).glob("fictional_scientist_quota_expanded_*.csv")
    )
    if not candidates:
        raise FileNotFoundError(
            f"fictional_scientist_quota_expanded_*.csv が見つかりません: {dir_path}"
        )
    if len(candidates) > 1:
        raise ValueError(
            f"expanded CSV が複数見つかりました ({len(candidates)} 件): {dir_path}"
        )
    return str(candidates[0])


def resolve_profile_output_path(dir_path: str) -> str:
    """--dir から profiles/ 以下の出力 JSONL パスを返す。"""
    return str(
        pathlib.Path(dir_path) / "profiles" / "fictional_scientist_profiles.jsonl"
    )


# ============================================================
# メイン
# ============================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="expanded CSV をもとにプロフィールを生成する"
    )
    parser.add_argument(
        "--dir",
        default=None,
        help="作業ディレクトリ (指定時は --input/--output を上書き)",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=MAX_ROWS_TO_GENERATE,
        help="処理する行数の上限 (デフォルト: %(default)s)",
    )
    parser.add_argument("--input", default=INPUT_CSV)
    parser.add_argument("--output", default=OUTPUT_JSONL)
    args = parser.parse_args()

    if args.dir is not None:
        input_csv = find_expanded_csv_in_dir(args.dir)
        output_jsonl = resolve_profile_output_path(args.dir)
    else:
        input_csv = args.input
        output_jsonl = args.output

    os.makedirs(os.path.dirname(output_jsonl), exist_ok=True)
    quota_rows = load_quota_rows(input_csv)
    existing_profiles = load_jsonl(output_jsonl)
    generated_profiles: List[Dict[str, Any]] = list(existing_profiles)
    total_created = 0

    for row in quota_rows:
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

        birth_year = random.randint(birth_year_start, birth_year_end)

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
            print(f"[profile_error] {scientist_id} err={e}")
            continue

        generated_profiles.append({**profile, "国籍": nationality, "主な分野": field})

        profile_record = {
            "id": scientist_id,
            "era": era,
            "gender": gender,
            "国籍": nationality,
            **profile,
        }
        append_jsonl(output_jsonl, profile_record)

        total_created += 1
        print(f"[ok] {total_created} ({scientist_id}): {nationality} / {field}")
        time.sleep(0.3)

    print(f"done: generated={total_created}")


if __name__ == "__main__":
    main()
