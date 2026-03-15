import csv

import pytest
from PIL import Image

from evaluate_portraits_embeddings import (
    EMBEDDING_EVALUATION_FIELDNAMES,
    build_embedding_evaluation_rows,
    compute_pairwise_metrics,
    cosine_similarity,
    discover_image_records,
    evaluate_image_records,
    normalize_embedding,
    resolve_embedding_evaluation_paths,
    write_embedding_evaluation_csv,
)


class FakeExtractor:
    def __init__(self, responses):
        self.responses = responses

    def extract(self, image_path):
        result = self.responses[image_path]
        if isinstance(result, Exception):
            raise result
        return result


class TestResolveEmbeddingEvaluationPaths:
    def test_正常系_portraitsディレクトリを自動解決する(self, tmp_path):
        portraits_dir = tmp_path / "sample_batch" / "portraits"
        portraits_dir.mkdir(parents=True)
        Image.new("RGB", (16, 16), color=(120, 120, 120)).save(
            portraits_dir / "s1.png"
        )

        image_dir, output_path, batch_name = resolve_embedding_evaluation_paths(
            str(tmp_path / "sample_batch")
        )

        assert image_dir == str(portraits_dir)
        assert output_path == str(tmp_path / "sample_batch" / "portrait_embedding_evaluation.csv")
        assert batch_name == "sample_batch"

    def test_正常系_画像ディレクトリ自体を入力できる(self, tmp_path):
        image_dir = tmp_path / "wikipedia_faces"
        image_dir.mkdir()
        Image.new("RGB", (16, 16), color=(120, 120, 120)).save(image_dir / "s1.jpg")

        resolved_image_dir, output_path, batch_name = resolve_embedding_evaluation_paths(
            str(image_dir)
        )

        assert resolved_image_dir == str(image_dir)
        assert output_path == str(tmp_path / "portrait_embedding_evaluation.csv")
        assert batch_name == tmp_path.name


class TestDiscoverImageRecords:
    def test_正常系_対応拡張子の画像だけを列挙する(self, tmp_path):
        Image.new("RGB", (16, 16), color=(100, 100, 100)).save(tmp_path / "b.png")
        Image.new("RGB", (16, 16), color=(120, 120, 120)).save(tmp_path / "a.jpg")
        (tmp_path / "memo.txt").write_text("ignore", encoding="utf-8")

        records = discover_image_records(str(tmp_path))

        assert records == [
            {"id": "a", "image_path": str(tmp_path / "a.jpg")},
            {"id": "b", "image_path": str(tmp_path / "b.png")},
        ]

    def test_異常系_画像が1枚も無いとエラーになる(self, tmp_path):
        with pytest.raises(ValueError):
            discover_image_records(str(tmp_path))


class TestNormalizeEmbedding:
    def test_正常系_l2正規化したベクトルを返す(self):
        normalized = normalize_embedding([3.0, 4.0])

        assert normalized == [0.6, 0.8]

    def test_異常系_ゼロベクトルはエラーになる(self):
        with pytest.raises(ValueError):
            normalize_embedding([0.0, 0.0])


class TestCosineSimilarity:
    def test_正常系_正規化ベクトル同士のコサイン類似度を返す(self):
        similarity = cosine_similarity([1.0, 0.0], [0.0, 1.0])

        assert similarity == 0.0


class TestComputePairwiseMetrics:
    def test_正常系_平均コサイン距離と最近傍距離を計算する(self):
        metrics = compute_pairwise_metrics(
            {
                "a": [1.0, 0.0],
                "b": [0.0, 1.0],
                "c": [1.0, 0.0],
            }
        )

        assert metrics["mean_pairwise_cosine_similarity"] == pytest.approx(1.0 / 3.0)
        assert metrics["batch_diversity_score"] == pytest.approx(2.0 / 3.0)
        assert metrics["nearest_neighbor_distance_by_id"]["a"] == pytest.approx(0.0)
        assert metrics["nearest_neighbor_distance_by_id"]["b"] == pytest.approx(1.0)


class TestBuildEmbeddingEvaluationRows:
    def test_正常系_成功行と失敗行をCSV向けに組み立てる(self, tmp_path):
        ok_path = tmp_path / "ok.png"
        ng_path = tmp_path / "ng.png"
        Image.new("RGB", (16, 16), color=(110, 110, 110)).save(ok_path)
        Image.new("RGB", (16, 16), color=(150, 150, 150)).save(ng_path)

        rows = build_embedding_evaluation_rows(
            image_records=[
                {"id": "ok", "image_path": str(ok_path)},
                {"id": "ng", "image_path": str(ng_path)},
            ],
            normalized_embeddings={"ok": [1.0, 0.0]},
            face_count_by_id={"ok": 1},
            error_by_id={"ng": "顔を検出できませんでした"},
            metrics={
                "mean_pairwise_cosine_similarity": 0.0,
                "batch_diversity_score": 1.0,
                "nearest_neighbor_distance_by_id": {"ok": 0.0},
                "nearest_neighbor_id_by_id": {"ok": "ok"},
            },
            batch_name="sample",
            model_name="buffalo_l",
        )

        assert rows[0]["status"] == "ok"
        assert rows[0]["embedding_json"] == "[1.0,0.0]"
        assert rows[1]["status"] == "error"
        assert rows[1]["error"] == "顔を検出できませんでした"
        assert list(rows[0].keys()) == EMBEDDING_EVALUATION_FIELDNAMES


class TestEvaluateImageRecords:
    def test_正常系_埋め込み評価サマリを返す(self, tmp_path):
        left_path = tmp_path / "left.png"
        right_path = tmp_path / "right.png"
        bad_path = tmp_path / "bad.png"
        Image.new("RGB", (16, 16), color=(100, 100, 100)).save(left_path)
        Image.new("RGB", (16, 16), color=(140, 140, 140)).save(right_path)
        Image.new("RGB", (16, 16), color=(180, 180, 180)).save(bad_path)

        extractor = FakeExtractor(
            {
                str(left_path): ([1.0, 0.0], 1),
                str(right_path): ([0.0, 1.0], 2),
                str(bad_path): ValueError("顔を検出できませんでした"),
            }
        )

        rows, summary = evaluate_image_records(
            image_records=[
                {"id": "left", "image_path": str(left_path)},
                {"id": "right", "image_path": str(right_path)},
                {"id": "bad", "image_path": str(bad_path)},
            ],
            extractor=extractor,
            batch_name="demo",
            model_name="buffalo_l",
        )

        assert len(rows) == 3
        assert summary["total_images"] == 3
        assert summary["embedded_images"] == 2
        assert summary["failed_images"] == 1
        assert summary["batch_diversity_score"] == pytest.approx(1.0)


class TestWriteEmbeddingEvaluationCsv:
    def test_正常系_評価CSVを書き出す(self, tmp_path):
        output_path = tmp_path / "portrait_embedding_evaluation.csv"
        rows = [
            {
                "batch_name": "sample",
                "id": "s1",
                "image_path": "sample/s1.png",
                "status": "ok",
                "face_count": "1",
                "nearest_neighbor_id": "s2",
                "nearest_neighbor_distance": "0.123456",
                "mean_pairwise_cosine_similarity": "0.654321",
                "batch_diversity_score": "0.345679",
                "embedding_model": "buffalo_l",
                "embedding_dimension": "2",
                "embedding_json": "[1.0,0.0]",
                "error": "",
            }
        ]

        write_embedding_evaluation_csv(str(output_path), rows)

        with open(output_path, encoding="utf-8", newline="") as file_obj:
            saved_rows = list(csv.DictReader(file_obj))

        assert saved_rows == rows
