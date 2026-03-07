import json


from generate_images import (
    filter_unprocessed,
    get_output_path,
    is_already_generated,
    load_portraits_jsonl,
)


class TestLoadPortraitsJsonl:
    def test_正常系_jsonlを正しく読み込む(self, tmp_path):
        jsonl_file = tmp_path / "test.jsonl"
        records = [
            {
                "id": 1,
                "名前": "ルキッラ",
                "era": "古代前期",
                "portrait_prompt": "A portrait...",
            },
            {
                "id": 2,
                "名前": "李明瓊",
                "era": "古代前期",
                "portrait_prompt": "Another portrait...",
            },
        ]
        with open(jsonl_file, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        result = load_portraits_jsonl(str(jsonl_file))

        assert len(result) == 2
        assert result[0]["名前"] == "ルキッラ"
        assert result[1]["名前"] == "李明瓊"

    def test_エッジケース_空ファイルで空リストを返す(self, tmp_path):
        jsonl_file = tmp_path / "empty.jsonl"
        jsonl_file.write_text("", encoding="utf-8")

        result = load_portraits_jsonl(str(jsonl_file))

        assert result == []

    def test_エッジケース_空行を含むファイルでも正常に読み込む(self, tmp_path):
        jsonl_file = tmp_path / "with_blank_lines.jsonl"
        jsonl_file.write_text(
            '{"名前": "テスト"}\n\n{"名前": "テスト2"}\n', encoding="utf-8"
        )

        result = load_portraits_jsonl(str(jsonl_file))

        assert len(result) == 2


class TestGetOutputPath:
    def test_正常系_文字列idからpngパスを生成する(self, tmp_path):
        path = get_output_path("古代前期__光学__古代ギリシア__0001", str(tmp_path))

        assert path.suffix == ".png"
        assert "古代前期__光学__古代ギリシア__0001" in path.name

    def test_正常系_idがファイル名にそのまま使われる(self, tmp_path):
        path = get_output_path("現代後期__物理学__日本__0042", str(tmp_path))

        assert path.name == "現代後期__物理学__日本__0042.png"

    def test_正常系_出力ディレクトリ配下に生成される(self, tmp_path):
        path = get_output_path("古代前期__光学__古代ギリシア__0001", str(tmp_path))

        assert path.parent == tmp_path

    def test_正常系_スラッシュを含むidがサニタイズされる(self, tmp_path):
        path = get_output_path("era/field/nationality/0001", str(tmp_path))

        assert "/" not in path.name


class TestIsAlreadyGenerated:
    def test_正常系_ファイルが存在する場合にTrueを返す(self, tmp_path):
        img_path = tmp_path / "test.png"
        img_path.write_bytes(b"dummy image data")

        assert is_already_generated(img_path) is True

    def test_正常系_ファイルが存在しない場合にFalseを返す(self, tmp_path):
        img_path = tmp_path / "nonexistent.png"

        assert is_already_generated(img_path) is False


class TestFilterUnprocessed:
    def test_正常系_処理済みのエントリが除外される(self, tmp_path):
        existing_path = get_output_path(
            "古代前期__光学__古代ギリシア__0001", str(tmp_path)
        )
        existing_path.write_bytes(b"dummy")

        entries = [
            {
                "id": "古代前期__光学__古代ギリシア__0001",
                "名前": "ルキッラ",
                "era": "古代前期",
                "portrait_prompt": "...",
            },
            {
                "id": "古代前期__光学__古代ギリシア__0002",
                "名前": "李明瓊",
                "era": "古代前期",
                "portrait_prompt": "...",
            },
        ]

        result = filter_unprocessed(entries, str(tmp_path))

        assert len(result) == 1
        assert result[0]["名前"] == "李明瓊"

    def test_正常系_全て未処理なら全件返す(self, tmp_path):
        entries = [
            {
                "id": "古代前期__光学__古代ギリシア__0001",
                "名前": "ルキッラ",
                "era": "古代前期",
                "portrait_prompt": "...",
            },
            {
                "id": "古代前期__光学__古代ギリシア__0002",
                "名前": "李明瓊",
                "era": "古代前期",
                "portrait_prompt": "...",
            },
        ]

        result = filter_unprocessed(entries, str(tmp_path))

        assert len(result) == 2

    def test_エッジケース_全て処理済みなら空リストを返す(self, tmp_path):
        entries = [
            {
                "id": "古代前期__光学__古代ギリシア__0001",
                "名前": "ルキッラ",
                "era": "古代前期",
                "portrait_prompt": "...",
            },
        ]
        for e in entries:
            path = get_output_path(e["id"], str(tmp_path))
            path.write_bytes(b"dummy")

        result = filter_unprocessed(entries, str(tmp_path))

        assert result == []

    def test_エッジケース_空リストなら空リストを返す(self, tmp_path):
        result = filter_unprocessed([], str(tmp_path))

        assert result == []
