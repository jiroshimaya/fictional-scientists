import argparse
import base64
import json
import os
import pathlib
import time
from typing import Any

from openai import OpenAI

# ============================================================
# 設定
# ============================================================

DEFAULT_DIR = "data/sample/two"
MODEL = "gpt-image-1.5"
IMAGE_SIZE = "1024x1024"
IMAGE_QUALITY = "low"

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


# ============================================================
# JSONL 読み込み
# ============================================================


def load_portraits_jsonl(path: str) -> list[dict[str, Any]]:
    """肖像画プロンプトのJSONLファイルを読み込む。"""
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


# ============================================================
# 出力パス管理
# ============================================================


def get_output_path(scientist_id: str, output_dir: str) -> pathlib.Path:
    """科学者 ID から画像の保存先パスを生成する。"""
    safe_id = str(scientist_id).replace("/", "_").replace("\\", "_")
    filename = f"{safe_id}.png"
    return pathlib.Path(output_dir) / filename


def resolve_images_paths(dir_path: str) -> tuple[str, str]:
    """--dir から input JSONL と output ディレクトリのパスを返す。"""
    input_path = str(pathlib.Path(dir_path) / "portrait_prompts.jsonl")
    output_dir = str(pathlib.Path(dir_path) / "portraits")
    return input_path, output_dir


def is_already_generated(path: pathlib.Path) -> bool:
    """画像が既に生成・保存済みかどうかを返す。"""
    return path.exists()


def filter_unprocessed(
    entries: list[dict[str, Any]], output_dir: str, force: bool = False
) -> list[dict[str, Any]]:
    """未処理（画像未生成）のエントリだけを返す。force=True のときは全件返す。"""
    if force:
        return list(entries)
    return [
        e
        for e in entries
        if not is_already_generated(get_output_path(e["id"], output_dir))
    ]


# ============================================================
# 画像生成
# ============================================================


def generate_image(api_client: OpenAI, prompt: str, model: str = MODEL) -> bytes:
    """DALL-E APIで画像を生成し、PNGバイト列を返す。"""
    response = api_client.images.generate(
        model=model,
        prompt=prompt,
        size=IMAGE_SIZE,
        quality=IMAGE_QUALITY,
        n=1,
    )
    b64_data = response.data[0].b64_json
    return base64.b64decode(b64_data)


def save_image(path: pathlib.Path, image_data: bytes) -> None:
    """画像データをファイルに保存する。出力ディレクトリは自動作成する。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image_data)


# ============================================================
# メイン
# ============================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="fictional_scientists_portraits.jsonl をもとに肖像画を生成する"
    )
    parser.add_argument(
        "--dir",
        default=DEFAULT_DIR,
        help="作業ディレクトリ (デフォルト: %(default)s)",
    )
    parser.add_argument(
        "--max-images",
        type=int,
        default=None,
        help="生成する最大画像数 (省略時: 全件)",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=1.0,
        help="API呼び出し間のスリープ秒数 (デフォルト: %(default)s)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="既存ファイルを無視して再生成する",
    )
    parser.add_argument(
        "--llm",
        default=MODEL,
        help="使用する画像生成モデル (デフォルト: %(default)s)",
    )
    args = parser.parse_args()

    input_jsonl, output_dir = resolve_images_paths(args.dir)

    entries = load_portraits_jsonl(input_jsonl)
    targets = filter_unprocessed(entries, output_dir, force=args.force)

    if args.max_images is not None:
        targets = targets[: args.max_images]

    print(f"生成対象: {len(targets)} 件 (全体 {len(entries)} 件中)")

    generated = 0
    for i, entry in enumerate(targets, 1):
        scientist_id = entry["id"]
        name = entry.get("名前", scientist_id)
        prompt = entry.get("portrait_prompt", "")
        output_path = get_output_path(scientist_id, output_dir)

        if not prompt:
            print(f"[skip] id={scientist_id} {name}: portrait_prompt が空")
            continue

        try:
            print(f"[{i}/{len(targets)}] 生成中: id={scientist_id} {name} ...")
            image_data = generate_image(client, prompt, model=args.llm)
            save_image(output_path, image_data)
            generated += 1
            print(f"[ok] id={scientist_id} {name} -> {output_path}")
        except Exception as e:
            print(f"[error] id={scientist_id} {name}: {e}")

        time.sleep(args.sleep)

    print(f"完了: {generated} 件生成")


if __name__ == "__main__":
    main()
