import csv
import pathlib

import pytest

from expand_quota import expand_quota


class TestExpandQuota:
    def _write_master(self, path: pathlib.Path, rows: list[dict]) -> None:
        fieldnames = ["era_order", "era_name", "birth_year_band", "birth_year_start", "birth_year_end", "field", "gender", "nationality_region", "nationality", "count"]
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def _read_output(self, path: pathlib.Path) -> list[dict]:
        with open(path, "r", encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    def test_正常系_count分だけ行が複製される(self, tmp_path):
        master = tmp_path / "master.csv"
        self._write_master(master, [
            {"era_order": 1, "era_name": "古代前期", "birth_year_band": "紀元前400–紀元前1",
             "birth_year_start": -400, "birth_year_end": -1, "field": "光学",
             "gender": "女性", "nationality_region": "東地中海", "nationality": "古代ギリシア", "count": 3},
        ])
        output = tmp_path / "expanded.csv"

        total = expand_quota(str(master), str(output))

        rows = self._read_output(output)
        assert total == 3
        assert len(rows) == 3

    def test_正常系_複数行が正しく展開される(self, tmp_path):
        master = tmp_path / "master.csv"
        self._write_master(master, [
            {"era_order": 1, "era_name": "古代前期", "birth_year_band": "紀元前400–紀元前1",
             "birth_year_start": -400, "birth_year_end": -1, "field": "光学",
             "gender": "女性", "nationality_region": "東地中海", "nationality": "古代ギリシア", "count": 2},
            {"era_order": 1, "era_name": "古代前期", "birth_year_band": "紀元前400–紀元前1",
             "birth_year_start": -400, "birth_year_end": -1, "field": "力学",
             "gender": "男性", "nationality_region": "東地中海", "nationality": "古代ギリシア", "count": 3},
        ])
        output = tmp_path / "expanded.csv"

        total = expand_quota(str(master), str(output))

        rows = self._read_output(output)
        assert total == 5
        assert len(rows) == 5

    def test_正常系_idがera_field_nationality_カウンタ形式で生成される(self, tmp_path):
        master = tmp_path / "master.csv"
        self._write_master(master, [
            {"era_order": 1, "era_name": "古代前期", "birth_year_band": "紀元前400–紀元前1",
             "birth_year_start": -400, "birth_year_end": -1, "field": "光学",
             "gender": "女性", "nationality_region": "東地中海", "nationality": "古代ギリシア", "count": 3},
        ])
        output = tmp_path / "expanded.csv"

        expand_quota(str(master), str(output))

        rows = self._read_output(output)
        assert rows[0]["id"] == "古代前期__光学__古代ギリシア__0001"
        assert rows[1]["id"] == "古代前期__光学__古代ギリシア__0002"
        assert rows[2]["id"] == "古代前期__光学__古代ギリシア__0003"

    def test_正常系_count列が出力に含まれない(self, tmp_path):
        master = tmp_path / "master.csv"
        self._write_master(master, [
            {"era_order": 1, "era_name": "古代前期", "birth_year_band": "紀元前400–紀元前1",
             "birth_year_start": -400, "birth_year_end": -1, "field": "光学",
             "gender": "女性", "nationality_region": "東地中海", "nationality": "古代ギリシア", "count": 2},
        ])
        output = tmp_path / "expanded.csv"

        expand_quota(str(master), str(output))

        rows = self._read_output(output)
        assert "count" not in rows[0]

    def test_正常系_id列が先頭列になる(self, tmp_path):
        master = tmp_path / "master.csv"
        self._write_master(master, [
            {"era_order": 1, "era_name": "古代前期", "birth_year_band": "紀元前400–紀元前1",
             "birth_year_start": -400, "birth_year_end": -1, "field": "光学",
             "gender": "女性", "nationality_region": "東地中海", "nationality": "古代ギリシア", "count": 1},
        ])
        output = tmp_path / "expanded.csv"

        expand_quota(str(master), str(output))

        with open(output, "r", encoding="utf-8") as f:
            header = f.readline().strip().split(",")
        assert header[0] == "id"

    def test_正常系_元の列の値が保持される(self, tmp_path):
        master = tmp_path / "master.csv"
        self._write_master(master, [
            {"era_order": 1, "era_name": "古代前期", "birth_year_band": "紀元前400–紀元前1",
             "birth_year_start": -400, "birth_year_end": -1, "field": "光学",
             "gender": "女性", "nationality_region": "東地中海", "nationality": "古代ギリシア", "count": 2},
        ])
        output = tmp_path / "expanded.csv"

        expand_quota(str(master), str(output))

        rows = self._read_output(output)
        for row in rows:
            assert row["era_name"] == "古代前期"
            assert row["nationality"] == "古代ギリシア"
            assert row["field"] == "光学"

    def test_エッジケース_count_1の行は1行だけ出力される(self, tmp_path):
        master = tmp_path / "master.csv"
        self._write_master(master, [
            {"era_order": 1, "era_name": "古代前期", "birth_year_band": "紀元前400–紀元前1",
             "birth_year_start": -400, "birth_year_end": -1, "field": "光学",
             "gender": "女性", "nationality_region": "東地中海", "nationality": "古代ギリシア", "count": 1},
        ])
        output = tmp_path / "expanded.csv"

        total = expand_quota(str(master), str(output))

        assert total == 1

    def test_正常系_異なるグループは独立したカウンタを持つ(self, tmp_path):
        master = tmp_path / "master.csv"
        self._write_master(master, [
            {"era_order": 1, "era_name": "古代前期", "birth_year_band": "紀元前400–紀元前1",
             "birth_year_start": -400, "birth_year_end": -1, "field": "光学",
             "gender": "女性", "nationality_region": "東地中海", "nationality": "古代ギリシア", "count": 2},
            {"era_order": 2, "era_name": "古代後期", "birth_year_band": "1–499",
             "birth_year_start": 1, "birth_year_end": 499, "field": "力学",
             "gender": "男性", "nationality_region": "南欧", "nationality": "ローマ共和政・帝政圏", "count": 3},
        ])
        output = tmp_path / "expanded.csv"

        expand_quota(str(master), str(output))

        rows = self._read_output(output)
        ids = [r["id"] for r in rows]
        assert ids[0] == "古代前期__光学__古代ギリシア__0001"
        assert ids[1] == "古代前期__光学__古代ギリシア__0002"
        assert ids[2] == "古代後期__力学__ローマ共和政・帝政圏__0001"
        assert ids[3] == "古代後期__力学__ローマ共和政・帝政圏__0002"
        assert ids[4] == "古代後期__力学__ローマ共和政・帝政圏__0003"
