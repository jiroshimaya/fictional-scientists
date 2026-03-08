"""
quota.csv / names.csv / profiles.jsonl / portraits/ をまとめたカタログCSVを生成する。
"""

import argparse
import csv
import json
import pathlib
from typing import Any

# ============================================================
# 定数
# ============================================================

CATALOG_FIELDNAMES = [
    "id",
    "era_order",
    "era_name",
    "field",
    "gender",
    "nationality_region",
    "nationality",
    "full_name",
    "last_name",
    "first_name",
    "full_name_reading",
    "last_name_reading",
    "first_name_reading",
    "birth_year",
    "death_year",
    "research_summary",
    "portrait_path",
    "portrait_exists",
]


# ============================================================
# 読み込み
# ============================================================


def load_quota_csv(path: str) -> dict[str, dict[str, Any]]:
    """quota.csv を id をキーとした辞書で返す。ファイルが存在しない場合は FileNotFoundError を送出。"""
    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(f"quota.csv が見つかりません: {path}")
    result: dict[str, dict[str, Any]] = {}
    with open(p, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            result[row["id"]] = dict(row)
    return result


def load_names_csv(path: str) -> dict[str, dict[str, str]]:
    """names.csv を id をキーとした辞書で返す。ファイルが存在しない場合は空辞書を返す。"""
    p = pathlib.Path(path)
    if not p.exists():
        return {}
    result: dict[str, dict[str, str]] = {}
    with open(p, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            result[row["id"]] = {
                "full_name": row.get("名前", ""),
                "last_name": row.get("姓", ""),
                "first_name": row.get("名", ""),
                "full_name_reading": row.get("ナマエ", ""),
                "last_name_reading": row.get("セイ", ""),
                "first_name_reading": row.get("メイ", ""),
            }
    return result


def load_profiles_jsonl(path: str) -> dict[str, dict[str, str]]:
    """profiles.jsonl を id をキーとした辞書で返す。ファイルが存在しない場合は空辞書を返す。"""
    p = pathlib.Path(path)
    if not p.exists():
        return {}
    result: dict[str, dict[str, str]] = {}
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            result[record["id"]] = {
                "birth_year": record.get("生年", ""),
                "death_year": record.get("没年", "") or "",
                "research_summary": record.get("研究内容（要約）", ""),
            }
    return result


def build_portrait_path(scientist_id: str, portraits_dir: str) -> tuple[str, bool]:
    """portraits/ 配下の画像パスと存在有無を返す。"""
    p = pathlib.Path(portraits_dir) / f"{scientist_id}.png"
    return str(p), p.exists()


# ============================================================
# カタログ生成
# ============================================================


def compile_catalog(dir_path: str, output_path: str) -> None:
    """dir_path 内の各ファイルを結合してカタログCSVを生成する。"""
    base = pathlib.Path(dir_path)

    quota = load_quota_csv(str(base / "quota.csv"))
    names = load_names_csv(str(base / "names.csv"))
    profiles = load_profiles_jsonl(str(base / "profiles.jsonl"))
    portraits_dir = str(base / "portraits")

    _empty_names = {
        k: ""
        for k in [
            "full_name",
            "last_name",
            "first_name",
            "full_name_reading",
            "last_name_reading",
            "first_name_reading",
        ]
    }
    _empty_profiles = {"birth_year": "", "death_year": "", "research_summary": ""}

    rows: list[dict[str, Any]] = []
    for scientist_id, quota_row in quota.items():
        portrait_path, portrait_exists = build_portrait_path(
            scientist_id, portraits_dir
        )
        row: dict[str, Any] = {
            "id": scientist_id,
            "era_order": quota_row.get("era_order", ""),
            "era_name": quota_row.get("era_name", ""),
            "field": quota_row.get("field", ""),
            "gender": quota_row.get("gender", ""),
            "nationality_region": quota_row.get("nationality_region", ""),
            "nationality": quota_row.get("nationality", ""),
            **names.get(scientist_id, _empty_names),
            **profiles.get(scientist_id, _empty_profiles),
            "portrait_path": portrait_path,
            "portrait_exists": portrait_exists,
        }
        rows.append(row)

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CATALOG_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


# ============================================================
# CLI
# ============================================================


def main() -> None:
    parser = argparse.ArgumentParser(description="カタログCSVを生成する")
    parser.add_argument(
        "--dir",
        required=True,
        help="入力ディレクトリ (quota.csv, names.csv, profiles.jsonl, portraits/)",
    )
    parser.add_argument("--output", help="出力CSVパス（省略時は --dir/catalog.csv）")
    args = parser.parse_args()

    output = args.output or str(pathlib.Path(args.dir) / "catalog.csv")
    compile_catalog(args.dir, output)
    print(f"生成完了: {output}")


if __name__ == "__main__":
    main()
