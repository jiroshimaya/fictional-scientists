import csv
from pathlib import Path

from download_scientists import (
    OutputPaths,
    api_get,
    build_output_paths,
    choose_image,
    get_first_p18,
    has_claim_value,
    process_pages,
    run,
)


class TestBuildOutputPaths:
    def test_正常系_output_dir配下に既定ファイルを解決する(self, tmp_path):
        paths = build_output_paths(tmp_path)

        assert paths.output_dir == tmp_path
        assert paths.titles_cache == tmp_path / "titles_ja_scientists.txt"
        assert paths.csv_path == tmp_path / "scientist_images.csv"


class TestApiGet:
    def test_正常系_429後に再試行してjsonを返す(self, monkeypatch):
        class _Response:
            def __init__(self, status_code, payload, headers=None):
                self.status_code = status_code
                self._payload = payload
                self.headers = headers or {}

            def json(self):
                return self._payload

            def raise_for_status(self):
                raise AssertionError("raise_for_status should not be called")

        class _Session:
            def __init__(self):
                self.calls = 0

            def get(self, url, params=None, timeout=None):
                self.calls += 1
                if self.calls == 1:
                    return _Response(429, {}, {"Retry-After": "0"})
                return _Response(200, {"query": {"ok": True}})

        monkeypatch.setattr("download_scientists.jitter", lambda *args, **kwargs: None)

        result = api_get(_Session(), "https://ja.wikipedia.org/w/api.php", {"action": "query"})

        assert result == {"query": {"ok": True}}


class TestClaimHelpers:
    def test_正常系_P31がtarget_qidならTrueを返す(self):
        entity = {
            "claims": {
                "P31": [
                    {
                        "mainsnak": {
                            "datavalue": {
                                "value": {"id": "Q5"},
                            }
                        }
                    }
                ]
            }
        }

        assert has_claim_value(entity, "P31", "Q5") is True

    def test_エッジケース_壊れたclaimでもFalseで継続する(self):
        entity = {"claims": {"P31": [{"mainsnak": {"datavalue": None}}, {}]}}

        assert has_claim_value(entity, "P31", "Q5") is False

    def test_正常系_最初のP18を返す(self):
        entity = {
            "claims": {
                "P18": [
                    {"mainsnak": {"datavalue": {"value": "Alpha.jpg"}}},
                    {"mainsnak": {"datavalue": {"value": "Beta.jpg"}}},
                ]
            }
        }

        assert get_first_p18(entity) == "Alpha.jpg"


class TestChooseImage:
    def test_正常系_page_image_freeを優先する(self):
        image_name, source = choose_image("Portrait.jpg", "P18.jpg")

        assert image_name == "Portrait.jpg"
        assert source == "page_image_free"

    def test_正常系_page_image_freeが図版ならP18へ退避する(self):
        image_name, source = choose_image("Scientist logo.svg", "Portrait.jpg")

        assert image_name == "Portrait.jpg"
        assert source == "P18"


class TestProcessPages:
    def test_正常系_人間のみを保存してcsvへ追記する(self, monkeypatch, tmp_path):
        pages = [
            {"title": "アルファ", "qid": "Q1", "page_image_free": "Alpha portrait.jpg"},
            {"title": "ベータ", "qid": "Q2", "page_image_free": None},
            {"title": "ガンマ", "qid": None, "page_image_free": None},
        ]
        entities = {
            "Q1": {
                "claims": {
                    "P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}],
                    "P18": [{"mainsnak": {"datavalue": {"value": "Alpha fallback.jpg"}}}],
                }
            },
            "Q2": {
                "claims": {
                    "P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q123"}}}}],
                }
            },
        }
        downloads: list[tuple[str, Path]] = []

        def fake_commons_imageinfo(session, filename):
            assert filename == "Alpha portrait.jpg"
            return {
                "url": "https://example.com/alpha.jpg",
                "license_short_name": "CC BY 4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
            }

        def fake_download_file(session, url, outpath, timeout=180):
            downloads.append((url, outpath))
            outpath.parent.mkdir(parents=True, exist_ok=True)
            outpath.write_bytes(b"image")

        monkeypatch.setattr("download_scientists.commons_imageinfo", fake_commons_imageinfo)
        monkeypatch.setattr("download_scientists.download_file", fake_download_file)
        monkeypatch.setattr("download_scientists.jitter", lambda *args, **kwargs: None)

        stats = process_pages(
            session=object(),
            pages=pages,
            entities=entities,
            paths=OutputPaths(
                output_dir=tmp_path,
                titles_cache=tmp_path / "titles.txt",
                csv_path=tmp_path / "scientist_images.csv",
            ),
        )

        assert stats.downloaded == 1
        assert stats.csv_appended == 1
        assert stats.skipped_nonhuman == 2
        assert downloads == [("https://example.com/alpha.jpg", tmp_path / "アルファ.jpg")]

        with (tmp_path / "scientist_images.csv").open(
            "r", encoding="utf-8", newline=""
        ) as f:
            rows = list(csv.DictReader(f))

        assert rows == [
            {
                "title_ja": "アルファ",
                "qid": "Q1",
                "image_name": "Alpha portrait.jpg",
                "image_url": "https://example.com/alpha.jpg",
                "license_short_name": "CC BY 4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "saved_path": str(tmp_path / "アルファ.jpg"),
                "source": "page_image_free",
            }
        ]


class TestRun:
    def test_正常系_タイトルキャッシュを優先して全体処理できる(self, monkeypatch, tmp_path):
        cache_path = tmp_path / "titles_ja_scientists.txt"
        cache_path.write_text("アルファ\n", encoding="utf-8")
        called = {"collect": 0}

        def fake_collect(session, root_category, base_sleep=0.8):
            called["collect"] += 1
            return ["should not be used"]

        def fake_pageprops(session, titles, base_sleep=0.45):
            assert titles == ["アルファ"]
            return [{"title": "アルファ", "qid": "Q1", "page_image_free": "Alpha.jpg"}]

        def fake_entities(session, qids, base_sleep=0.35):
            assert qids == ["Q1"]
            return {
                "Q1": {
                    "claims": {
                        "P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}],
                        "P18": [{"mainsnak": {"datavalue": {"value": "Alpha alt.jpg"}}}],
                    }
                }
            }

        def fake_commons_imageinfo(session, filename):
            assert filename == "Alpha.jpg"
            return {
                "url": "https://example.com/alpha.jpg",
                "license_short_name": "CC BY 4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
            }

        def fake_download_file(session, url, outpath, timeout=180):
            outpath.parent.mkdir(parents=True, exist_ok=True)
            outpath.write_bytes(b"alpha")

        monkeypatch.setattr(
            "download_scientists.get_category_members_recursive",
            fake_collect,
        )
        monkeypatch.setattr("download_scientists.get_pageprops_for_titles", fake_pageprops)
        monkeypatch.setattr("download_scientists.get_wikidata_entities", fake_entities)
        monkeypatch.setattr("download_scientists.commons_imageinfo", fake_commons_imageinfo)
        monkeypatch.setattr("download_scientists.download_file", fake_download_file)
        monkeypatch.setattr("download_scientists.jitter", lambda *args, **kwargs: None)

        stats = run(output_dir=tmp_path, session=object())

        assert called["collect"] == 0
        assert stats.downloaded == 1
        assert stats.csv_appended == 1
        assert (tmp_path / "アルファ.jpg").exists()
