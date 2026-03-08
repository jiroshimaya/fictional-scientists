"""
全体の分布を反映した1000件のサンプル quota CSV を生成するスクリプト。

生成物:
  data/sample/distribution_1000/quota.csv  (1000件)

戦略:
  data/all/quota.csv (10000件) から時代 (era_order) ごとに
  層化サンプリング（各時代 10%）し、IDを振り直す。
"""

import csv
import pathlib
import random
from collections import defaultdict

random.seed(42)

TARGET = 1000
TOTAL = 10000
RATIO = TARGET / TOTAL  # 0.1

FIELDNAMES = [
    "id",
    "era_order",
    "era_name",
    "birth_year_band",
    "birth_year_start",
    "birth_year_end",
    "field",
    "gender",
    "nationality_region",
    "nationality",
]

# 全データ読込
with open("data/all/quota.csv", encoding="utf-8", newline="") as f:
    all_rows = list(csv.DictReader(f))

# era_order ごとにグルーピング
groups: defaultdict = defaultdict(list)
for r in all_rows:
    groups[r["era_order"]].append(r)

# 時代ごとに比例サンプリング
sampled: list[dict] = []
for era_order in sorted(groups.keys(), key=lambda x: int(x)):
    grp = groups[era_order]
    n = round(len(grp) * RATIO)
    picked = random.sample(grp, n)
    sampled.extend(picked)

# 1000件に微調整（丸め誤差の吸収）
diff = TARGET - len(sampled)
if diff > 0:
    picked_ids = {r["id"] for r in sampled}
    remain = [r for r in all_rows if r["id"] not in picked_ids]
    sampled.extend(random.sample(remain, diff))
elif diff < 0:
    sampled = sampled[:TARGET]

# ID を era_name__field__nationality__NNNN 形式で振り直し
group_counter: defaultdict = defaultdict(int)
out_rows: list[dict] = []
for r in sampled:
    key = (r["era_name"], r["field"], r["nationality"])
    group_counter[key] += 1
    n = group_counter[key]
    new_id = f"{r['era_name']}__{r['field']}__{r['nationality']}__{n:04d}"
    out_rows.append({**r, "id": new_id})

# era_order → field → nationality → id でソート
out_rows.sort(key=lambda x: (int(x["era_order"]), x["field"], x["nationality"], x["id"]))

out_dir = pathlib.Path("data/sample/distribution_1000")
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "quota.csv"

with open(out_path, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
    writer.writeheader()
    for r in out_rows:
        writer.writerow({k: r[k] for k in FIELDNAMES})

print(f"生成完了: {out_path}  ({len(out_rows)} 件)")

# 分布確認
era_sample_counts: defaultdict = defaultdict(int)
for r in out_rows:
    era_sample_counts[r["era_name"]] += 1

print("\n時代別件数（サンプル / 全体 = 比率）:")
for era_order in sorted(groups.keys(), key=lambda x: int(x)):
    era = groups[era_order][0]["era_name"]
    sc = era_sample_counts[era]
    tc = len(groups[era_order])
    print(f"  {era:24s}: {sc:4d} / {tc:4d} = {sc/tc*100:.1f}%")
