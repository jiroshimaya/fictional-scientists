"""
顔埋め込みベクトルにもとづいて肖像画像バッチの多様性を評価する。
"""

import argparse
import csv
import json
import math
import pathlib
from typing import Protocol

from PIL import Image

DEFAULT_DIR = "data/sample/two"
DEFAULT_OUTPUT_FILE = "portrait_embedding_evaluation.csv"
DEFAULT_IMAGE_SUBDIRS = ("portraits", "wikipedia_faces")
DEFAULT_MODEL_NAME = "buffalo_l"
DEFAULT_PROVIDERS = ("CPUExecutionProvider",)
DEFAULT_DET_SIZE = 640
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

EMBEDDING_EVALUATION_FIELDNAMES = [
    "batch_name",
    "id",
    "image_path",
    "status",
    "face_count",
    "nearest_neighbor_id",
    "nearest_neighbor_distance",
    "mean_pairwise_cosine_similarity",
    "batch_diversity_score",
    "embedding_model",
    "embedding_dimension",
    "embedding_json",
    "error",
]


class FaceEmbeddingExtractor(Protocol):
    def extract(self, image_path: str) -> tuple[list[float], int]:
        """画像から顔埋め込みベクトルと検出顔数を返す。"""


def resolve_embedding_evaluation_paths(
    dir_path: str,
    image_dir: str | None = None,
    output_path: str | None = None,
    batch_name: str | None = None,
) -> tuple[str, str, str]:
    """入力画像ディレクトリ、出力CSV、バッチ名を解決する。"""
    base_dir = pathlib.Path(dir_path)
    resolved_image_dir = pathlib.Path(image_dir) if image_dir else _detect_image_dir(base_dir)
    if not resolved_image_dir.exists():
        raise FileNotFoundError(
            f"画像ディレクトリが見つかりません: {resolved_image_dir}"
        )

    batch_root = _resolve_batch_root(base_dir, resolved_image_dir)
    resolved_output_path = pathlib.Path(output_path) if output_path else batch_root / DEFAULT_OUTPUT_FILE
    resolved_batch_name = batch_name or batch_root.name or resolved_image_dir.name
    return (
        str(resolved_image_dir),
        str(resolved_output_path),
        resolved_batch_name,
    )


def _detect_image_dir(base_dir: pathlib.Path) -> pathlib.Path:
    if _has_supported_images(base_dir):
        return base_dir

    for subdir_name in DEFAULT_IMAGE_SUBDIRS:
        candidate = base_dir / subdir_name
        if _has_supported_images(candidate):
            return candidate

    raise FileNotFoundError(
        "画像ディレクトリを解決できませんでした。"
        f" {base_dir} 自体、または {', '.join(DEFAULT_IMAGE_SUBDIRS)} に画像を配置してください。"
    )


def _resolve_batch_root(base_dir: pathlib.Path, image_dir: pathlib.Path) -> pathlib.Path:
    if image_dir == base_dir:
        if image_dir.name in DEFAULT_IMAGE_SUBDIRS:
            return image_dir.parent
        return image_dir
    return base_dir


def _has_supported_images(path: pathlib.Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    return any(
        child.is_file() and child.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
        for child in path.iterdir()
    )


def discover_image_records(image_dir: str) -> list[dict[str, str]]:
    """評価対象画像を列挙する。"""
    image_dir_path = pathlib.Path(image_dir)
    if not image_dir_path.exists():
        raise FileNotFoundError(f"画像ディレクトリが見つかりません: {image_dir}")

    image_paths = sorted(
        path
        for path in image_dir_path.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
    )
    if not image_paths:
        raise ValueError(f"画像ファイルが見つかりません: {image_dir}")

    return [{"id": path.stem, "image_path": str(path)} for path in image_paths]


def normalize_embedding(embedding: list[float]) -> list[float]:
    """L2正規化した埋め込みベクトルを返す。"""
    norm = math.sqrt(sum(value * value for value in embedding))
    if norm == 0:
        raise ValueError("zero embedding is not allowed")
    return [value / norm for value in embedding]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """2つの正規化済みベクトルのコサイン類似度を返す。"""
    if len(left) != len(right):
        raise ValueError("embedding length mismatch")
    return sum(lhs * rhs for lhs, rhs in zip(left, right))


def compute_pairwise_metrics(
    embeddings: dict[str, list[float]],
) -> dict[str, float | dict[str, str] | dict[str, float]]:
    """ペアワイズのコサイン距離と最近傍距離を集計する。"""
    item_ids = list(embeddings.keys())
    if len(item_ids) < 2:
        return {
            "mean_pairwise_cosine_similarity": 0.0,
            "batch_diversity_score": 0.0,
            "nearest_neighbor_distance_by_id": {},
            "nearest_neighbor_id_by_id": {},
        }

    pairwise_similarities: list[float] = []
    nearest_neighbor_distance_by_id: dict[str, float] = {
        item_id: float("inf") for item_id in item_ids
    }
    nearest_neighbor_id_by_id: dict[str, str] = {}

    for index, left_id in enumerate(item_ids):
        for right_id in item_ids[index + 1 :]:
            similarity = cosine_similarity(embeddings[left_id], embeddings[right_id])
            distance = 1.0 - similarity
            pairwise_similarities.append(similarity)
            _update_nearest_neighbor(
                left_id,
                right_id,
                distance,
                nearest_neighbor_distance_by_id,
                nearest_neighbor_id_by_id,
            )
            _update_nearest_neighbor(
                right_id,
                left_id,
                distance,
                nearest_neighbor_distance_by_id,
                nearest_neighbor_id_by_id,
            )

    mean_pairwise_cosine_similarity = sum(pairwise_similarities) / len(
        pairwise_similarities
    )
    return {
        "mean_pairwise_cosine_similarity": mean_pairwise_cosine_similarity,
        "batch_diversity_score": 1.0 - mean_pairwise_cosine_similarity,
        "nearest_neighbor_distance_by_id": nearest_neighbor_distance_by_id,
        "nearest_neighbor_id_by_id": nearest_neighbor_id_by_id,
    }


def _update_nearest_neighbor(
    item_id: str,
    candidate_id: str,
    distance: float,
    nearest_neighbor_distance_by_id: dict[str, float],
    nearest_neighbor_id_by_id: dict[str, str],
) -> None:
    current_distance = nearest_neighbor_distance_by_id[item_id]
    current_neighbor = nearest_neighbor_id_by_id.get(item_id, "")
    if (
        distance < current_distance
        or (distance == current_distance and candidate_id < current_neighbor)
    ):
        nearest_neighbor_distance_by_id[item_id] = distance
        nearest_neighbor_id_by_id[item_id] = candidate_id


def evaluate_image_records(
    image_records: list[dict[str, str]],
    extractor: FaceEmbeddingExtractor,
    batch_name: str,
    model_name: str,
) -> tuple[list[dict[str, str]], dict[str, float | int | str]]:
    """画像一覧を評価してCSV行とサマリを返す。"""
    normalized_embeddings: dict[str, list[float]] = {}
    face_count_by_id: dict[str, int] = {}
    error_by_id: dict[str, str] = {}

    for record in image_records:
        item_id = record["id"]
        image_path = record["image_path"]
        try:
            embedding, face_count = extractor.extract(image_path)
        except (FileNotFoundError, ValueError) as exc:
            error_by_id[item_id] = str(exc)
            continue

        normalized_embeddings[item_id] = normalize_embedding(embedding)
        face_count_by_id[item_id] = face_count

    metrics = compute_pairwise_metrics(normalized_embeddings)
    rows = build_embedding_evaluation_rows(
        image_records=image_records,
        normalized_embeddings=normalized_embeddings,
        face_count_by_id=face_count_by_id,
        error_by_id=error_by_id,
        metrics=metrics,
        batch_name=batch_name,
        model_name=model_name,
    )

    nearest_neighbor_distances = [
        value
        for value in metrics["nearest_neighbor_distance_by_id"].values()
        if isinstance(value, float) and math.isfinite(value)
    ]
    summary = {
        "batch_name": batch_name,
        "total_images": len(image_records),
        "embedded_images": len(normalized_embeddings),
        "failed_images": len(error_by_id),
        "mean_pairwise_cosine_similarity": float(
            metrics["mean_pairwise_cosine_similarity"]
        ),
        "batch_diversity_score": float(metrics["batch_diversity_score"]),
        "mean_nearest_neighbor_distance": (
            sum(nearest_neighbor_distances) / len(nearest_neighbor_distances)
            if nearest_neighbor_distances
            else 0.0
        ),
    }
    return rows, summary


def build_embedding_evaluation_rows(
    image_records: list[dict[str, str]],
    normalized_embeddings: dict[str, list[float]],
    face_count_by_id: dict[str, int],
    error_by_id: dict[str, str],
    metrics: dict[str, float | dict[str, str] | dict[str, float]],
    batch_name: str,
    model_name: str,
) -> list[dict[str, str]]:
    """埋め込み評価CSVの行を組み立てる。"""
    nearest_neighbor_distance_by_id = metrics["nearest_neighbor_distance_by_id"]
    nearest_neighbor_id_by_id = metrics["nearest_neighbor_id_by_id"]
    mean_pairwise_cosine_similarity = float(metrics["mean_pairwise_cosine_similarity"])
    batch_diversity_score = float(metrics["batch_diversity_score"])

    rows: list[dict[str, str]] = []
    for record in image_records:
        item_id = record["id"]
        embedding = normalized_embeddings.get(item_id)
        distance = nearest_neighbor_distance_by_id.get(item_id)
        rows.append(
            {
                "batch_name": batch_name,
                "id": item_id,
                "image_path": record["image_path"],
                "status": "ok" if embedding is not None else "error",
                "face_count": str(face_count_by_id.get(item_id, "")),
                "nearest_neighbor_id": str(nearest_neighbor_id_by_id.get(item_id, "")),
                "nearest_neighbor_distance": (
                    _format_float(distance) if isinstance(distance, float) else ""
                ),
                "mean_pairwise_cosine_similarity": _format_float(
                    mean_pairwise_cosine_similarity
                ),
                "batch_diversity_score": _format_float(batch_diversity_score),
                "embedding_model": model_name if embedding is not None else "",
                "embedding_dimension": str(len(embedding) if embedding is not None else ""),
                "embedding_json": (
                    json.dumps(embedding, ensure_ascii=False, separators=(",", ":"))
                    if embedding is not None
                    else ""
                ),
                "error": error_by_id.get(item_id, ""),
            }
        )
    return rows


def write_embedding_evaluation_csv(path: str, rows: list[dict[str, str]]) -> None:
    """評価結果CSVを書き出す。"""
    with open(path, "w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=EMBEDDING_EVALUATION_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _format_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}"


class InsightFaceExtractor:
    """InsightFace を使って顔埋め込みベクトルを抽出する。"""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        providers: tuple[str, ...] = DEFAULT_PROVIDERS,
        det_size: int = DEFAULT_DET_SIZE,
    ) -> None:
        try:
            import numpy as np
            from insightface.app import FaceAnalysis
        except ImportError as exc:
            raise RuntimeError(
                "InsightFace の依存関係が未インストールです。"
                " `uv sync` で依存関係を導入してください。"
            ) from exc

        self._numpy = np
        self._face_app = FaceAnalysis(name=model_name, providers=list(providers))
        self._face_app.prepare(ctx_id=0, det_size=(det_size, det_size))

    def extract(self, image_path: str) -> tuple[list[float], int]:
        image = _load_rgb_image(image_path)
        image_bgr = self._numpy.array(image)[:, :, ::-1]
        faces = self._face_app.get(image_bgr)
        if not faces:
            raise ValueError(f"顔を検出できませんでした: {image_path}")

        primary_face = max(
            faces,
            key=lambda face: (face.bbox[2] - face.bbox[0]) * (face.bbox[3] - face.bbox[1]),
        )
        embedding = getattr(primary_face, "normed_embedding", None)
        if embedding is None:
            embedding = primary_face.embedding
        return list(embedding.tolist()), len(faces)


def _load_rgb_image(image_path: str) -> Image.Image:
    with Image.open(image_path) as image:
        return image.convert("RGB")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="顔埋め込みベクトルを使って肖像画像バッチの多様性を評価する"
    )
    parser.add_argument(
        "--dir",
        default=DEFAULT_DIR,
        help="入力ディレクトリ。画像を含むディレクトリ、または portraits/ / wikipedia_faces/ を含む親ディレクトリ。",
    )
    parser.add_argument(
        "--image-dir",
        default=None,
        help="画像ディレクトリを明示指定する場合に使う。",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="出力CSVパス（省略時は portrait_embedding_evaluation.csv）",
    )
    parser.add_argument(
        "--batch-name",
        default=None,
        help="CSVに書き出すバッチ名（省略時は入力ディレクトリ名）",
    )
    parser.add_argument(
        "--model-name",
        default=DEFAULT_MODEL_NAME,
        help=f"InsightFace のモデル名 (デフォルト: {DEFAULT_MODEL_NAME})",
    )
    parser.add_argument(
        "--providers",
        default=",".join(DEFAULT_PROVIDERS),
        help="ONNX Runtime providers をカンマ区切りで指定する。",
    )
    parser.add_argument(
        "--det-size",
        type=int,
        default=DEFAULT_DET_SIZE,
        help=f"顔検出時の det_size (デフォルト: {DEFAULT_DET_SIZE})",
    )
    args = parser.parse_args()

    image_dir, output_path, batch_name = resolve_embedding_evaluation_paths(
        dir_path=args.dir,
        image_dir=args.image_dir,
        output_path=args.output,
        batch_name=args.batch_name,
    )
    image_records = discover_image_records(image_dir)
    providers = tuple(
        provider.strip() for provider in args.providers.split(",") if provider.strip()
    )
    extractor = InsightFaceExtractor(
        model_name=args.model_name,
        providers=providers or DEFAULT_PROVIDERS,
        det_size=args.det_size,
    )
    rows, summary = evaluate_image_records(
        image_records=image_records,
        extractor=extractor,
        batch_name=batch_name,
        model_name=args.model_name,
    )
    write_embedding_evaluation_csv(output_path, rows)

    print(f"evaluation_csv={output_path}")
    print(f"batch_name={summary['batch_name']}")
    print(f"total_images={summary['total_images']}")
    print(f"embedded_images={summary['embedded_images']}")
    print(f"failed_images={summary['failed_images']}")
    print(
        "mean_pairwise_cosine_similarity="
        f"{summary['mean_pairwise_cosine_similarity']:.6f}"
    )
    print(f"batch_diversity_score={summary['batch_diversity_score']:.6f}")
    print(
        "mean_nearest_neighbor_distance="
        f"{summary['mean_nearest_neighbor_distance']:.6f}"
    )


if __name__ == "__main__":
    main()
