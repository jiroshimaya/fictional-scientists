"""
fictional_scientist_quota_master_10000.csv の各行を count の数だけ複製し、
複合 id 列（era_name__field__nationality__NNNN 形式）を付与した展開済み CSV を出力する。
"""

import argparse
import csv
from collections import defaultdict

MASTER_CSV = "data/attributes/fictional_scientist_quota_master_10000.csv"
OUTPUT_CSV = "data/attributes/fictional_scientist_quota_expanded_10000.csv"


def expand_quota(master_path: str, output_path: str) -> int:
    """master CSV を count 数だけ展開して複合 id を付与し output に書き出す。総行数を返す。"""
    expanded_rows: list[dict] = []
    group_counter: defaultdict = defaultdict(int)

    with open(master_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            count = int(row.get("count") or 1)
            era_name = row["era_name"]
            field = row["field"]
            nationality = row["nationality"]

            for _ in range(count):
                group_counter[(era_name, field, nationality)] += 1
                n = group_counter[(era_name, field, nationality)]
                scientist_id = f"{era_name}__{field}__{nationality}__{n:04d}"
                expanded_rows.append({**row, "id": scientist_id})

    if not expanded_rows:
        return 0

    source_fields = [c for c in expanded_rows[0].keys() if c not in ("count", "id")]
    output_fields = ["id"] + source_fields

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=output_fields)
        writer.writeheader()
        for row in expanded_rows:
            writer.writerow({k: row[k] for k in output_fields})

    return len(expanded_rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="quota master CSV を展開して id 付き CSV を生成する"
    )
    parser.add_argument("--input", default=MASTER_CSV, help="入力マスターCSV")
    parser.add_argument("--output", default=OUTPUT_CSV, help="出力展開済みCSV")
    args = parser.parse_args()

    n = expand_quota(args.input, args.output)
    print(f"展開完了: {n} 行 -> {args.output}")


if __name__ == "__main__":
    main()
