"""
profiles JSONL をもとに架空科学者の肖像画プロンプトを生成する。
"""

import argparse
import json
import os
import pathlib
import time
from typing import Any, Dict, List

from openai import OpenAI

# ============================================================
# 設定
# ============================================================

MODEL = "gpt-4.1-mini"
DEFAULT_DIR = "data/sample/two"
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
    },
    "required": ["portrait_prompt"],
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
- portrait_prompt は日本語で記述すること
- 出力はJSONのみ
"""

_PORTRAIT_ERA_CONTEXTS: Dict[str, Dict[str, str]] = {
    "古代前期": {
        "medium": (
            "時代に合致した以下の形式から一つを選んでください: "
            "断片的な石彫レリーフ、風化した大理石彫刻バスト、テラコッタの小像、"
            "損傷したフレスコ壁画断片、部分的に修復されたモザイク肖像"
        ),
        "preservation": (
            "激しく風化、部分的に損傷、一部の特徴が磨耗して失われている、"
            "断片的または復元済み、古代石材の経年色"
        ),
        "pose": (
            "石に刻まれた正面または横顔、着座した正式なポーズ、"
            "立った儀式的なポーズ、または部分的なバストの断片"
        ),
    },
    "古代後期": {
        "medium": (
            "以下から一つを選んでください: 大理石バスト肖像、モザイク肖像、"
            "エンカウスティック蝋パネル画（ファイユームの肖像風）、フレスコ"
        ),
        "preservation": "風化、一部の色が褪色または消失、経年のパティナ、軽微な損傷",
        "pose": "正面向き、四分の三アングル、または正式に着座",
    },
    "中世前期": {
        "medium": (
            "以下から一つを選んでください: ビザンチン様式のイコン（金地、平面的な様式化されたスタイル）、"
            "彩飾写本のミニアチュール、フレスコ"
        ),
        "preservation": "色の褪色、わずかに損傷した縁、経年した羊皮紙または漆喰",
        "pose": "正面向きの正式なポーズ、様式化された表現、学術的または宗教的な場面での着座",
    },
    "中世後期": {
        "medium": (
            "以下から一つを選んでください: 彩飾写本の挿絵、"
            "石彫の墓石像または墓彫刻、フレスコ、初期パネル画"
        ),
        "preservation": "経年、わずかに褪色、軽微な損傷、中世的な特徴",
        "pose": (
            "半正面または四分の三アングル、着座して書いているか立っている、"
            "正式な中世的ポーズ"
        ),
    },
    "ルネサンス・初期近世": {
        "medium": (
            "以下から一つを選んでください: パネルまたはキャンバスに油彩画、"
            "銅版画または木版画、テンペラ画"
        ),
        "preservation": (
            "わずかに黄変した経年キャンバスまたは紙、クラックルール（亀裂模様）、"
            "その時代としては良好に保存"
        ),
        "pose": (
            "四分の三アングル、横顔、半身または全身、"
            "ルネサンス時代の背景で着座または立っている"
        ),
    },
    "近世前期": {
        "medium": (
            "以下から一つを選んでください: キャンバスに油彩肖像画、"
            "エッチングまたはメゾチント版画、パステル画"
        ),
        "preservation": "経年キャンバスまたは紙、ニスのわずかな暗化、良好に保存",
        "pose": (
            "四分の三アングル、机に着座または立っている、"
            "物や本と共にバロック様式の正式なポーズ"
        ),
    },
    "近世後期": {
        "medium": "以下から一つを選んでください: 油彩肖像画、パステル肖像画、銅版画、チョーク素描",
        "preservation": "経年しているが良好に保存、わずかな黄変、18世紀の特徴",
        "pose": ("四分の三アングル、着座した正式なポーズ、半身、" "科学機器や本と共に"),
    },
    "近代前期": {
        "medium": (
            "以下から一つを選んでください: 油彩肖像画、水彩肖像画、リトグラフ、"
            "初期ダゲレオタイプ（1840年代後半の人物を描く場合のみ）"
        ),
        "preservation": "良好に保存、わずかな経年、19世紀のスタイル",
        "pose": "正式に着座または立っている、四分の三アングル、半身肖像画",
    },
    "近代後期": {
        "medium": (
            "写真肖像画 — アルブミン印画紙、銀ゼラチン印画紙、またはキャビネット判写真"
        ),
        "preservation": (
            "わずかに黄変または褪色した写真、ヴィンテージのシルバートーン、良好に保存"
        ),
        "pose": (
            "正式に着座（ヴィクトリア朝・明治時代の写真で一般的）、"
            "四分の三アングル、スタジオでの立ちポーズ、または実験器具と共に"
        ),
    },
    "現代前期": {
        "medium": "白黒写真",
        "preservation": "良好に保存、クラシックなモノクローム",
        "pose": (
            "正式またはセミフォーマル、四分の三アングル、着座または立っている、"
            "オフィス・実験室・屋外の場面"
        ),
    },
    "現代中期": {
        "medium": "カラーまたは白黒写真",
        "preservation": "良好に保存",
        "pose": ("多様: 正式、屋外、実験室、会議、四分の三または正面"),
    },
    "現代後期": {
        "medium": "カラー写真またはデジタル写真",
        "preservation": "良好に保存、モダン",
        "pose": (
            "多様: プロフェッショナル、カジュアル、屋外、実験室の場面、四分の三または正面"
        ),
    },
    "現代最年少": {
        "medium": "デジタル写真",
        "preservation": "モダン、鮮明",
        "pose": (
            "多様: プロフェッショナルなヘッドショット、カジュアル、実験室、四分の三または正面"
        ),
    },
}


def _get_portrait_era_context(era_name: str) -> Dict[str, str]:
    """時代名に基づいてポートレートの媒体・保存状態・ポーズ情報を返す。"""
    return _PORTRAIT_ERA_CONTEXTS.get(
        era_name,
        {
            "medium": "時代に応じた油彩肖像画または写真",
            "preservation": "経年または良好に保存",
            "pose": "四分の三アングル、着座または立っている",
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
- portrait_prompt は日本語で記述すること
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


def resolve_portrait_prompt_paths(dir_path: str) -> tuple[str, str]:
    """--dir から input JSONL と output JSONL のパスを返す。"""
    input_path = str(pathlib.Path(dir_path) / "profiles.jsonl")
    output_path = str(pathlib.Path(dir_path) / "portrait_prompts.jsonl")
    return input_path, output_path


# ============================================================
# 生成ロジック
# ============================================================


def generate_one_portrait_prompt(
    profile: Dict[str, Any],
    era: str,
    gender: str,
    model: str = MODEL,
) -> Dict[str, Any]:
    user_prompt = build_portrait_user_prompt(profile=profile, era=era, gender=gender)
    return create_structured_json(
        model=model,
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
        "--dir",
        default=DEFAULT_DIR,
        help="作業ディレクトリ (デフォルト: %(default)s)",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=MAX_ROWS_TO_GENERATE,
        help="処理する行数の上限 (デフォルト: %(default)s)",
    )
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

    input_profiles, output_jsonl = resolve_portrait_prompt_paths(args.dir)

    if args.force:
        pathlib.Path(output_jsonl).unlink(missing_ok=True)

    profile_records = load_jsonl(input_profiles)
    existing_portraits = load_jsonl(output_jsonl)
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
                model=args.llm,
            )
        except Exception as e:
            print(f"[portrait_error] {scientist_id} err={e}")
            portrait = {"portrait_prompt": ""}

        portrait_record = {
            "id": scientist_id,
            "era": era,
            "gender": gender,
            "nationality": record.get("国籍", ""),
            "field": record.get("主な分野", ""),
            **portrait,
        }
        append_jsonl(output_jsonl, portrait_record)

        total_created += 1
        print(f"[ok] {total_created} ({scientist_id})")
        time.sleep(0.3)

    print(f"done: generated={total_created}")


if __name__ == "__main__":
    main()
