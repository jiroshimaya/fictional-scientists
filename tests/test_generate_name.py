import csv
import pathlib

import pytest

from generate_name import (
    NAME_SCHEMA,
    NAME_SYSTEM_PROMPT,
    build_name_user_prompt,
    find_expanded_csv_in_dir,
    is_id_name_generated,
    load_existing_names,
    resolve_name_output_path,
)


class TestLoadExistingNames:
    def _write_names_csv(self, path: pathlib.Path, rows: list[dict]) -> None:
        fieldnames = ["id", "名前", "姓", "名", "ナマエ", "セイ", "メイ"]
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_正常系_CSVからidをキーとした辞書を返す(self, tmp_path):
        csv_file = tmp_path / "names.csv"
        self._write_names_csv(
            csv_file,
            [
                {
                    "id": "古代前期__光学__古代ギリシア__0001",
                    "名前": "テスト",
                    "姓": "テ",
                    "名": "スト",
                    "ナマエ": "テスト",
                    "セイ": "テ",
                    "メイ": "スト",
                },
            ],
        )

        result = load_existing_names(str(csv_file))

        assert "古代前期__光学__古代ギリシア__0001" in result
        assert result["古代前期__光学__古代ギリシア__0001"]["名前"] == "テスト"

    def test_エッジケース_ファイルが存在しない場合に空辞書を返す(self, tmp_path):
        result = load_existing_names(str(tmp_path / "nonexistent.csv"))

        assert result == {}

    def test_正常系_複数行を読み込める(self, tmp_path):
        csv_file = tmp_path / "names.csv"
        self._write_names_csv(
            csv_file,
            [
                {
                    "id": "id1",
                    "名前": "テスト1",
                    "姓": "テ",
                    "名": "スト1",
                    "ナマエ": "テスト1",
                    "セイ": "テ",
                    "メイ": "スト1",
                },
                {
                    "id": "id2",
                    "名前": "テスト2",
                    "姓": "テ",
                    "名": "スト2",
                    "ナマエ": "テスト2",
                    "セイ": "テ",
                    "メイ": "スト2",
                },
            ],
        )

        result = load_existing_names(str(csv_file))

        assert len(result) == 2
        assert "id1" in result
        assert "id2" in result


class TestIsIdNameGenerated:
    def test_正常系_存在するidでTrueを返す(self):
        existing = {"id1": {"名前": "テスト"}, "id2": {"名前": "テスト2"}}

        assert is_id_name_generated(existing, "id1") is True

    def test_正常系_存在しないidでFalseを返す(self):
        existing = {"id1": {"名前": "テスト"}}

        assert is_id_name_generated(existing, "id_unknown") is False

    def test_エッジケース_空辞書でFalseを返す(self):
        assert is_id_name_generated({}, "id1") is False

    def test_正常系_複合idでも判定できる(self):
        existing = {"古代前期__光学__古代ギリシア__0001": {"名前": "テスト"}}

        assert (
            is_id_name_generated(existing, "古代前期__光学__古代ギリシア__0001") is True
        )
        assert (
            is_id_name_generated(existing, "古代前期__光学__古代ギリシア__0002")
            is False
        )


class TestBuildNameUserPrompt:
    def test_正常系_プロンプトに時代が含まれる(self):
        prompt = build_name_user_prompt(
            era="古代前期",
            gender="女性",
            nationality="古代ギリシア",
            field="光学",
            recent_names=[],
        )

        assert "古代前期" in prompt

    def test_正常系_プロンプトに国籍が含まれる(self):
        prompt = build_name_user_prompt(
            era="古代前期",
            gender="女性",
            nationality="古代ギリシア",
            field="光学",
            recent_names=[],
        )

        assert "古代ギリシア" in prompt

    def test_正常系_プロンプトに性別が含まれる(self):
        prompt = build_name_user_prompt(
            era="古代前期",
            gender="女性",
            nationality="古代ギリシア",
            field="光学",
            recent_names=[],
        )

        assert "女性" in prompt

    def test_正常系_最近の名前がプロンプトに含まれる(self):
        prompt = build_name_user_prompt(
            era="古代前期",
            gender="女性",
            nationality="古代ギリシア",
            field="光学",
            recent_names=["テスト太郎"],
        )

        assert "テスト太郎" in prompt


class TestFindExpandedCsvInDir:
    def test_正常系_1つのexpanded_csvを発見してパスを返す(self, tmp_path):
        csv_file = tmp_path / "fictional_scientist_quota_expanded_sample.csv"
        csv_file.touch()

        result = find_expanded_csv_in_dir(str(tmp_path))

        assert result == str(csv_file)

    def test_異常系_csvが存在しない場合FileNotFoundErrorを送出する(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            find_expanded_csv_in_dir(str(tmp_path))

    def test_異常系_csvが複数ある場合ValueErrorを送出する(self, tmp_path):
        (tmp_path / "fictional_scientist_quota_expanded_a.csv").touch()
        (tmp_path / "fictional_scientist_quota_expanded_b.csv").touch()

        with pytest.raises(ValueError):
            find_expanded_csv_in_dir(str(tmp_path))

    def test_エッジケース_パターンに一致しないcsvは無視される(self, tmp_path):
        (tmp_path / "other_file.csv").touch()
        (tmp_path / "fictional_scientist_quota_expanded_sample.csv").touch()

        result = find_expanded_csv_in_dir(str(tmp_path))

        assert "expanded" in result


class TestResolveNameOutputPath:
    def test_正常系_dirからnames配下のcsvパスを返す(self, tmp_path):
        result = resolve_name_output_path(str(tmp_path))

        expected = str(tmp_path / "names" / "fictional_scientist_names.csv")
        assert result == expected

    def test_正常系_最近の名前が空の場合でも文字列を返す(self):
        prompt = build_name_user_prompt(
            era="古代前期",
            gender="女性",
            nationality="古代ギリシア",
            field="光学",
            recent_names=[],
        )

        assert isinstance(prompt, str)
        assert len(prompt) > 0


class TestNameSchema:
    def test_正常系_姓がnullable型である(self):
        sei_schema = NAME_SCHEMA["properties"]["姓"]

        assert "anyOf" in sei_schema
        types = [t["type"] for t in sei_schema["anyOf"]]
        assert "string" in types
        assert "null" in types

    def test_正常系_セイがnullable型である(self):
        sei_kana_schema = NAME_SCHEMA["properties"]["セイ"]

        assert "anyOf" in sei_kana_schema
        types = [t["type"] for t in sei_kana_schema["anyOf"]]
        assert "string" in types
        assert "null" in types


class TestNameSystemPrompt:
    def test_正常系_単名制文化への言及が含まれる(self):
        assert "単名制" in NAME_SYSTEM_PROMPT
