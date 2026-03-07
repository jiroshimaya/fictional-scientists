import csv
import pathlib


from generate_name import (
    build_name_user_prompt,
    is_id_name_generated,
    load_existing_names,
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
