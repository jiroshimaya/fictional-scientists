import io
import csv
from urllib.error import HTTPError

import pytest

from download_wikipedia_faces import (
    WikipediaImageNotFoundError,
    build_summary_url,
    download_image_bytes,
    download_face_image,
    extract_image_url,
    fetch_page_summary,
    filter_unprocessed_rows,
    find_existing_output_path,
    get_output_path,
    get_retry_delay,
    guess_extension,
    load_input_rows,
    resolve_page_title,
    resolve_wikipedia_paths,
)


class TestLoadInputRows:
    def test_正常系_csvを読み込んで辞書リストを返す(self, tmp_path):
        csv_path = tmp_path / "scientists.csv"
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "名前", "wikipedia_title"])
            writer.writeheader()
            writer.writerow(
                {
                    "id": "einstein",
                    "名前": "アルベルト・アインシュタイン",
                    "wikipedia_title": "Albert Einstein",
                }
            )

        rows = load_input_rows(str(csv_path))

        assert rows == [
            {
                "id": "einstein",
                "名前": "アルベルト・アインシュタイン",
                "wikipedia_title": "Albert Einstein",
            }
        ]


class TestResolveWikipediaPaths:
    def test_正常系_dirからcatalogと出力ディレクトリを解決する(self, tmp_path):
        input_path, output_dir = resolve_wikipedia_paths(str(tmp_path))

        assert input_path == str(tmp_path / "scientists.csv")
        assert output_dir == str(tmp_path / "wikipedia_faces")


class TestResolvePageTitle:
    def test_正常系_wikipedia_title列を優先して返す(self):
        row = {
            "名前": "アルベルト・アインシュタイン",
            "wikipedia_title": "Albert Einstein",
        }

        assert resolve_page_title(row) == "Albert Einstein"

    def test_正常系_wikipedia_titleが空なら名前列を返す(self):
        row = {"名前": "アルベルト・アインシュタイン", "wikipedia_title": " "}

        assert resolve_page_title(row) == "アルベルト・アインシュタイン"

    def test_異常系_名前もtitleも空ならValueErrorを送出する(self):
        row = {"名前": " ", "wikipedia_title": ""}

        with pytest.raises(ValueError):
            resolve_page_title(row)


class TestBuildSummaryUrl:
    def test_正常系_言語付きsummary_urlを組み立てる(self):
        url = build_summary_url("Albert Einstein", language="en")

        assert (
            url == "https://en.wikipedia.org/api/rest_v1/page/summary/Albert_Einstein"
        )

    def test_正常系_日本語タイトルをurlエンコードする(self):
        url = build_summary_url("アルベルト・アインシュタイン", language="ja")

        assert "%E3%82%A2" in url


class TestRetryHandling:
    def test_正常系_retry_afterヘッダを待機秒に使う(self):
        error = HTTPError(
            url="https://example.com",
            code=429,
            msg="Too Many Requests",
            hdrs={"Retry-After": "2"},
            fp=io.BytesIO(b""),
        )

        assert get_retry_delay(error, attempt=1) == 2.0

    def test_正常系_summary取得で429後に再試行できる(self, monkeypatch):
        responses = [
            HTTPError(
                url="https://example.com",
                code=429,
                msg="Too Many Requests",
                hdrs={"Retry-After": "0"},
                fp=io.BytesIO(b""),
            ),
            io.BytesIO(b'{"originalimage":{"source":"https://example.com/a.jpg"}}'),
        ]

        class _Response:
            def __init__(self, payload: io.BytesIO):
                self.payload = payload

            def read(self):
                return self.payload.read()

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        def fake_urlopen(request, timeout=None):
            current = responses.pop(0)
            if isinstance(current, HTTPError):
                raise current
            return _Response(current)

        monkeypatch.setattr("download_wikipedia_faces.urlopen", fake_urlopen)
        monkeypatch.setattr("download_wikipedia_faces.time.sleep", lambda _: None)

        result = fetch_page_summary("Albert Einstein")

        assert result["originalimage"]["source"] == "https://example.com/a.jpg"

    def test_正常系_画像取得で429後に再試行できる(self, monkeypatch):
        responses = [
            HTTPError(
                url="https://example.com",
                code=429,
                msg="Too Many Requests",
                hdrs={"Retry-After": "0"},
                fp=io.BytesIO(b""),
            ),
            io.BytesIO(b"image-bytes"),
        ]

        class _Response:
            def __init__(self, payload: io.BytesIO):
                self.payload = payload

            def read(self):
                return self.payload.read()

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        def fake_urlopen(request, timeout=None):
            current = responses.pop(0)
            if isinstance(current, HTTPError):
                raise current
            return _Response(current)

        monkeypatch.setattr("download_wikipedia_faces.urlopen", fake_urlopen)
        monkeypatch.setattr("download_wikipedia_faces.time.sleep", lambda _: None)

        result = download_image_bytes("https://example.com/a.jpg")

        assert result == b"image-bytes"


class TestExtractImageUrl:
    def test_正常系_originalimageを優先して返す(self):
        summary = {
            "originalimage": {"source": "https://upload.wikimedia.org/example.jpg"},
            "thumbnail": {"source": "https://upload.wikimedia.org/thumb.jpg"},
        }

        assert extract_image_url(summary) == "https://upload.wikimedia.org/example.jpg"

    def test_正常系_originalimageがなければthumbnailを返す(self):
        summary = {
            "thumbnail": {"source": "https://upload.wikimedia.org/thumb.jpg"},
        }

        assert extract_image_url(summary) == "https://upload.wikimedia.org/thumb.jpg"

    def test_異常系_画像情報がなければ専用例外を送出する(self):
        with pytest.raises(WikipediaImageNotFoundError):
            extract_image_url({})


class TestGuessExtension:
    def test_正常系_urlから拡張子を推定する(self):
        assert guess_extension("https://upload.wikimedia.org/example.png") == ".png"

    def test_エッジケース_拡張子不明ならjpgを返す(self):
        assert guess_extension("https://upload.wikimedia.org/example") == ".jpg"


class TestGetOutputPath:
    def test_正常系_id列を使って出力パスを作る(self, tmp_path):
        row = {"id": "einstein", "名前": "Albert Einstein"}

        output_path = get_output_path(
            row, str(tmp_path), image_url="https://example.com/a.jpg"
        )

        assert output_path == tmp_path / "einstein.jpg"

    def test_正常系_idのスラッシュをサニタイズする(self, tmp_path):
        row = {"id": "physics/einstein", "名前": "Albert Einstein"}

        output_path = get_output_path(
            row, str(tmp_path), image_url="https://example.com/a.jpg"
        )

        assert output_path.name == "physics_einstein.jpg"


class TestFindExistingOutputPath:
    def test_正常系_同じstemの既存画像を見つける(self, tmp_path):
        existing = tmp_path / "einstein.png"
        existing.write_bytes(b"image")

        found = find_existing_output_path(
            {"id": "einstein", "名前": "Albert Einstein"}, str(tmp_path)
        )

        assert found == existing

    def test_正常系_存在しなければNoneを返す(self, tmp_path):
        found = find_existing_output_path(
            {"id": "einstein", "名前": "Albert Einstein"}, str(tmp_path)
        )

        assert found is None


class TestFilterUnprocessedRows:
    def test_正常系_既存画像がある行を除外する(self, tmp_path):
        (tmp_path / "einstein.jpg").write_bytes(b"image")
        rows = [
            {"id": "einstein", "名前": "Albert Einstein"},
            {"id": "curie", "名前": "Marie Curie"},
        ]

        result = filter_unprocessed_rows(rows, str(tmp_path))

        assert result == [{"id": "curie", "名前": "Marie Curie"}]

    def test_正常系_force指定時は全件返す(self, tmp_path):
        (tmp_path / "einstein.jpg").write_bytes(b"image")
        rows = [{"id": "einstein", "名前": "Albert Einstein"}]

        result = filter_unprocessed_rows(rows, str(tmp_path), force=True)

        assert result == rows


class TestDownloadFaceImage:
    def test_正常系_summary画像を保存して保存先パスを返す(self, tmp_path, monkeypatch):
        row = {"id": "einstein", "名前": "Albert Einstein"}

        monkeypatch.setattr(
            "download_wikipedia_faces.fetch_page_summary",
            lambda title, language="ja": {
                "originalimage": {"source": "https://upload.wikimedia.org/einstein.jpg"}
            },
        )
        monkeypatch.setattr(
            "download_wikipedia_faces.download_image_bytes",
            lambda image_url: b"binary-image",
        )

        saved_path = download_face_image(
            row=row, output_dir=str(tmp_path), language="en"
        )

        assert saved_path == tmp_path / "einstein.jpg"
        assert saved_path.read_bytes() == b"binary-image"
