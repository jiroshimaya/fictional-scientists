"""
expanded CSV をもとに架空科学者の名前（名前・姓・名・ナマエ・セイ・メイ）を生成する。
生成済み id はスキップ。
"""

import argparse
import csv
import difflib
import json
import os
import pathlib
import time
from functools import lru_cache
from typing import Any, Dict, List

from openai import OpenAI

MODEL = "gpt-4.1-mini"
DEFAULT_DIR = "data/sample/two"
MAX_ROWS = 50
NAME_FIELDNAMES = ["id", "名前", "姓", "名", "ナマエ", "セイ", "メイ"]
NAME_SIMILARITY_THRESHOLD = 0.90

NAME_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "名前": {"type": "string"},
        "姓": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "名": {"type": "string"},
        "ナマエ": {"type": "string"},
        "セイ": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "メイ": {"type": "string"},
    },
    "required": ["名前", "姓", "名", "ナマエ", "セイ", "メイ"],
}

NAME_SYSTEM_PROMPT = """
あなたは科学史・人名学に詳しい創作支援AIです。
架空科学者の名前（名前・姓・名・読み仮名）を生成します。

重要:
- 実在人物と同じ名前を生成しない
- 時代・国籍・文化に自然な名前にする
- 「名前」は姓名を自然な順序で表記（東アジアは姓・名、欧米は名・姓）
- 「姓」「名」は個別のパーツ（文化により異なる分け方）
- 「ナマエ」「セイ」「メイ」はカタカナ読み。外国語名は発音に近いカタカナ表記
- 単名制文化（古代ギリシア・アケメネス朝ペルシア・古代インドなど）では姓が存在しないため、「姓」「セイ」はnullにする
- 出力はJSONのみ
"""


def build_name_user_prompt(
    era: str,
    gender: str,
    nationality: str,
    field: str,
    recent_names: List[str],
) -> str:
    recent_block = "\n".join(f"- {n}" for n in recent_names[-20:]) or "なし"
    return f"""
以下の属性に基づいて、架空の科学者の名前を1名分生成してください。

【入力】
- 時代区分: {era}
- 性別: {gender}
- 国籍: {nationality}
- 主な分野: {field}

【要件】
- 時代・国籍・文化圏に自然に合う名前を選ぶ
- 実在人物と同名は避ける
- ノンバイナリー／その他の場合は、その文化圏で存在しうる中性的または文脈依存的な名前にする

【最近生成した名前（被らないようにしてください）】
{recent_block}
"""


def normalize_text(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


def looks_duplicate_name(candidate_name: str, existing_names: List[str]) -> bool:
    return any(
        similarity(candidate_name, n) >= NAME_SIMILARITY_THRESHOLD
        for n in existing_names
    )


def load_existing_names(path: str) -> Dict[str, Dict[str, str]]:
    """名前 CSV を読み込み、id をキーとした辞書を返す。ファイルが存在しない場合は空辞書。"""
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            return {r["id"]: r for r in csv.DictReader(f)}
    except FileNotFoundError:
        return {}


def is_id_name_generated(existing: Dict[str, Any], scientist_id: str) -> bool:
    """指定した id の名前が既に生成済みかどうかを返す。"""
    return scientist_id in existing


def load_quota_rows(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=1)
def get_openai_client() -> OpenAI:
    """OPENAI_API_KEY を使って OpenAI クライアントを返す。"""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=api_key)


def create_structured_json(
    model: str,
    system_prompt: str,
    user_prompt: str,
    schema_name: str,
    schema: Dict[str, Any],
) -> Dict[str, Any]:
    resp = get_openai_client().responses.create(
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


def generate_one_name(
    era: str,
    gender: str,
    nationality: str,
    field: str,
    existing_names: List[str],
    max_attempts: int = 5,
    model: str = MODEL,
) -> Dict[str, str]:
    for attempt in range(1, max_attempts + 1):
        user_prompt = build_name_user_prompt(
            era=era,
            gender=gender,
            nationality=nationality,
            field=field,
            recent_names=existing_names[-20:],
        )
        name_data = create_structured_json(
            model=model,
            system_prompt=NAME_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            schema_name="scientist_name",
            schema=NAME_SCHEMA,
        )
        if not looks_duplicate_name(name_data["名前"], existing_names):
            return name_data
        time.sleep(0.3)
    raise RuntimeError(
        f"Failed to generate non-duplicate name after {max_attempts} attempts"
    )


def append_name_csv(
    path: str, record: Dict[str, str], fieldnames: List[str] = NAME_FIELDNAMES
) -> None:
    """名前 CSV に1行追記する。ファイルが存在しない場合はヘッダーも書く。"""
    file_path = pathlib.Path(path)
    file_exists = file_path.exists()
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(record)


def resolve_quota_input_path(dir_path: str) -> str:
    """--dir から quota.csv のパスを返す。"""
    return str(pathlib.Path(dir_path) / "quota.csv")


def resolve_name_output_path(dir_path: str) -> str:
    """--dir から names.csv のパスを返す。"""
    return str(pathlib.Path(dir_path) / "names.csv")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="expanded CSV をもとに名前を生成して CSV に保存する"
    )
    parser.add_argument(
        "--dir",
        default=DEFAULT_DIR,
        help="作業ディレクトリ (デフォルト: %(default)s)",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=MAX_ROWS,
        help="生成する最大件数 (デフォルト: %(default)s)",
    )
    parser.add_argument("--sleep", type=float, default=0.3)
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="既存ファイルを無視して再生成する",
    )
    parser.add_argument(
        "--llm",
        default=MODEL,
        help="使用するLLMモデル (デフォルト: %(default)s)",
    )
    args = parser.parse_args()

    input_csv = resolve_quota_input_path(args.dir)
    output_csv = resolve_name_output_path(args.dir)

    if args.force:
        pathlib.Path(output_csv).unlink(missing_ok=True)

    quota_rows = load_quota_rows(input_csv)
    existing = load_existing_names(output_csv)
    existing_name_list = [r["名前"] for r in existing.values()]

    generated = 0
    for row in quota_rows:
        if generated >= args.max_rows:
            break

        scientist_id = row["id"]
        if is_id_name_generated(existing, scientist_id):
            print(f"[skip] {scientist_id}")
            continue

        era = row["era_name"]
        gender = row["gender"]
        nationality = row["nationality"]
        field = row["field"]

        try:
            name_data = generate_one_name(
                era=era,
                gender=gender,
                nationality=nationality,
                field=field,
                existing_names=existing_name_list,
                model=args.llm,
            )
        except Exception as e:
            print(f"[error] {scientist_id}: {e}")
            continue

        record: Dict[str, str] = {"id": scientist_id, **name_data}
        append_name_csv(output_csv, record)
        existing[scientist_id] = record
        existing_name_list.append(name_data["名前"])
        generated += 1
        print(f"[ok] {scientist_id}: {name_data['名前']}")
        time.sleep(args.sleep)

    print(f"完了: {generated} 件生成")


if __name__ == "__main__":
    main()
