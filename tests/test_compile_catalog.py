import csv
import json
import pathlib

import pytest

from compile_catalog import (
    load_quota_csv,
    load_names_csv,
    load_profiles_jsonl,
    build_portrait_path,
    compile_catalog,
    CATALOG_FIELDNAMES,
)


# ============================================================
# load_quota_csv
# ============================================================


class TestLoadQuotaCsv:
    def _write_quota(self, path: pathlib.Path, rows: list[dict]) -> None:
        fieldnames = [
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
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_正常系_idをキーとした辞書を返す(self, tmp_path):
        csv_file = tmp_path / "quota.csv"
        self._write_quota(
            csv_file,
            [
                {
                    "id": "古代前期__自然哲学__古代ギリシア__0001",
                    "era_order": "1",
                    "era_name": "古代前期",
                    "birth_year_band": "紀元前400–紀元前1",
                    "birth_year_start": "-400",
                    "birth_year_end": "-1",
                    "field": "自然哲学",
                    "gender": "男性",
                    "nationality_region": "東地中海",
                    "nationality": "古代ギリシア",
                }
            ],
        )

        result = load_quota_csv(str(csv_file))

        assert "古代前期__自然哲学__古代ギリシア__0001" in result
        assert (
            result["古代前期__自然哲学__古代ギリシア__0001"]["era_name"] == "古代前期"
        )
        assert result["古代前期__自然哲学__古代ギリシア__0001"]["era_order"] == "1"

    def test_エッジケース_ファイルが存在しない場合にエラーを発生させる(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_quota_csv(str(tmp_path / "nonexistent.csv"))


# ============================================================
# load_names_csv
# ============================================================


class TestLoadNamesCsv:
    def _write_names(self, path: pathlib.Path, rows: list[dict]) -> None:
        fieldnames = ["id", "名前", "姓", "名", "ナマエ", "セイ", "メイ"]
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_正常系_idをキーとした辞書を返す(self, tmp_path):
        csv_file = tmp_path / "names.csv"
        self._write_names(
            csv_file,
            [
                {
                    "id": "古代前期__自然哲学__古代ギリシア__0001",
                    "名前": "デイノクラテス",
                    "姓": "",
                    "名": "デイノクラテス",
                    "ナマエ": "デイノクラテス",
                    "セイ": "",
                    "メイ": "デイノクラテス",
                }
            ],
        )

        result = load_names_csv(str(csv_file))

        assert "古代前期__自然哲学__古代ギリシア__0001" in result
        assert (
            result["古代前期__自然哲学__古代ギリシア__0001"]["full_name"]
            == "デイノクラテス"
        )
        assert result["古代前期__自然哲学__古代ギリシア__0001"]["last_name"] == ""
        assert (
            result["古代前期__自然哲学__古代ギリシア__0001"]["first_name"]
            == "デイノクラテス"
        )
        assert (
            result["古代前期__自然哲学__古代ギリシア__0001"]["full_name_reading"]
            == "デイノクラテス"
        )
        assert (
            result["古代前期__自然哲学__古代ギリシア__0001"]["last_name_reading"] == ""
        )
        assert (
            result["古代前期__自然哲学__古代ギリシア__0001"]["first_name_reading"]
            == "デイノクラテス"
        )

    def test_エッジケース_ファイルが存在しない場合に空辞書を返す(self, tmp_path):
        result = load_names_csv(str(tmp_path / "nonexistent.csv"))

        assert result == {}


# ============================================================
# load_profiles_jsonl
# ============================================================


class TestLoadProfilesJsonl:
    def _write_profiles(self, path: pathlib.Path, records: list[dict]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def test_正常系_idをキーとした辞書を返す(self, tmp_path):
        jsonl_file = tmp_path / "profiles.jsonl"
        self._write_profiles(
            jsonl_file,
            [
                {
                    "id": "古代前期__自然哲学__古代ギリシア__0001",
                    "era": "古代前期",
                    "gender": "男性",
                    "国籍": "古代ギリシア",
                    "主な分野": "自然哲学",
                    "生年": "紀元前4世紀末頃",
                    "没年": "紀元前280年頃",
                    "研究内容（要約）": "感覚器官と自然界の結びつきを論じた",
                }
            ],
        )

        result = load_profiles_jsonl(str(jsonl_file))

        assert "古代前期__自然哲学__古代ギリシア__0001" in result
        assert (
            result["古代前期__自然哲学__古代ギリシア__0001"]["birth_year"]
            == "紀元前4世紀末頃"
        )
        assert (
            result["古代前期__自然哲学__古代ギリシア__0001"]["death_year"]
            == "紀元前280年頃"
        )
        assert (
            result["古代前期__自然哲学__古代ギリシア__0001"]["research_summary"]
            == "感覚器官と自然界の結びつきを論じた"
        )

    def test_エッジケース_ファイルが存在しない場合に空辞書を返す(self, tmp_path):
        result = load_profiles_jsonl(str(tmp_path / "nonexistent.jsonl"))

        assert result == {}


# ============================================================
# build_portrait_path
# ============================================================


class TestBuildPortraitPath:
    def test_正常系_portraits配下のpngパスを返す(self, tmp_path):
        portraits_dir = tmp_path / "portraits"
        portraits_dir.mkdir()
        (portraits_dir / "古代前期__自然哲学__古代ギリシア__0001.png").touch()

        path, exists = build_portrait_path(
            scientist_id="古代前期__自然哲学__古代ギリシア__0001",
            portraits_dir=str(portraits_dir),
        )

        assert path.endswith("古代前期__自然哲学__古代ギリシア__0001.png")
        assert exists is True

    def test_正常系_画像が存在しない場合にexistsがFalse(self, tmp_path):
        portraits_dir = tmp_path / "portraits"
        portraits_dir.mkdir()

        path, exists = build_portrait_path(
            scientist_id="古代前期__自然哲学__古代ギリシア__0001",
            portraits_dir=str(portraits_dir),
        )

        assert exists is False

    def test_正常系_portraits_dirが存在しない場合にexistsがFalse(self, tmp_path):
        path, exists = build_portrait_path(
            scientist_id="古代前期__自然哲学__古代ギリシア__0001",
            portraits_dir=str(tmp_path / "portraits"),
        )

        assert exists is False


# ============================================================
# compile_catalog
# ============================================================


class TestCompileCatalog:
    def _setup_dir(self, tmp_path: pathlib.Path) -> pathlib.Path:
        """quota.csv / names.csv / profiles.jsonl / portraits/ を用意する。"""
        quota_rows = [
            {
                "id": "古代前期__自然哲学__古代ギリシア__0001",
                "era_order": "1",
                "era_name": "古代前期",
                "birth_year_band": "紀元前400–紀元前1",
                "birth_year_start": "-400",
                "birth_year_end": "-1",
                "field": "自然哲学",
                "gender": "男性",
                "nationality_region": "東地中海",
                "nationality": "古代ギリシア",
            }
        ]
        fieldnames = [
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
        with open(tmp_path / "quota.csv", "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(quota_rows)

        name_rows = [
            {
                "id": "古代前期__自然哲学__古代ギリシア__0001",
                "名前": "デイノクラテス",
                "姓": "",
                "名": "デイノクラテス",
                "ナマエ": "デイノクラテス",
                "セイ": "",
                "メイ": "デイノクラテス",
            }
        ]
        with open(tmp_path / "names.csv", "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["id", "名前", "姓", "名", "ナマエ", "セイ", "メイ"]
            )
            writer.writeheader()
            writer.writerows(name_rows)

        profiles = [
            {
                "id": "古代前期__自然哲学__古代ギリシア__0001",
                "生年": "紀元前4世紀末頃",
                "没年": "紀元前280年頃",
                "研究内容（要約）": "感覚器官と自然界の結びつきを論じた",
            }
        ]
        with open(tmp_path / "profiles.jsonl", "w", encoding="utf-8") as f:
            for r in profiles:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        portraits_dir = tmp_path / "portraits"
        portraits_dir.mkdir()
        (portraits_dir / "古代前期__自然哲学__古代ギリシア__0001.png").touch()

        return tmp_path

    def test_正常系_全列を持つ1行のCSVが生成される(self, tmp_path):
        dir_path = self._setup_dir(tmp_path)
        output_path = tmp_path / "catalog.csv"

        compile_catalog(str(dir_path), str(output_path))

        assert output_path.exists()
        with open(output_path, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1
        row = rows[0]
        assert row["id"] == "古代前期__自然哲学__古代ギリシア__0001"
        assert row["era_order"] == "1"
        assert row["era_name"] == "古代前期"
        assert row["field"] == "自然哲学"
        assert row["gender"] == "男性"
        assert row["nationality_region"] == "東地中海"
        assert row["nationality"] == "古代ギリシア"
        assert row["full_name"] == "デイノクラテス"
        assert row["birth_year"] == "紀元前4世紀末頃"
        assert row["death_year"] == "紀元前280年頃"
        assert row["research_summary"] == "感覚器官と自然界の結びつきを論じた"
        assert row["portrait_exists"] == "True"

    def test_正常系_namesがない場合は名前列が空文字になる(self, tmp_path):
        dir_path = self._setup_dir(tmp_path)
        (dir_path / "names.csv").unlink()
        output_path = tmp_path / "catalog.csv"

        compile_catalog(str(dir_path), str(output_path))

        with open(output_path, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        assert rows[0]["full_name"] == ""

    def test_正常系_profilesがない場合はプロフィール列が空文字になる(self, tmp_path):
        dir_path = self._setup_dir(tmp_path)
        (dir_path / "profiles.jsonl").unlink()
        output_path = tmp_path / "catalog.csv"

        compile_catalog(str(dir_path), str(output_path))

        with open(output_path, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        assert rows[0]["birth_year"] == ""
        assert rows[0]["research_summary"] == ""

    def test_正常系_画像がない場合はportrait_existsがFalse(self, tmp_path):
        dir_path = self._setup_dir(tmp_path)
        for f in (dir_path / "portraits").iterdir():
            f.unlink()
        output_path = tmp_path / "catalog.csv"

        compile_catalog(str(dir_path), str(output_path))

        with open(output_path, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        assert rows[0]["portrait_exists"] == "False"

    def test_正常系_CATALOG_FIELDNAMESが期待する列を持つ(self):
        expected = [
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
        assert CATALOG_FIELDNAMES == expected
