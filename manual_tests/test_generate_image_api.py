"""
手動テスト: generate_images.py の generate_image 関数を実際のAPIで動作確認する。

実行方法:
    uv run manual_tests/test_generate_image_api.py

環境変数 OPENAI_API_KEY が必要。
1件だけ画像を生成して data/portraits/ に保存する。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI

from generate_images import (
    DEFAULT_DIR,
    generate_image,
    load_portraits_jsonl,
    resolve_images_paths,
    save_image,
    get_output_path,
)


def main() -> None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY が設定されていません")
        sys.exit(1)

    api_client = OpenAI(api_key=api_key)

    input_jsonl, output_dir = resolve_images_paths(DEFAULT_DIR)

    entries = load_portraits_jsonl(input_jsonl)
    if not entries:
        print("ERROR: JSONLファイルにエントリがありません")
        sys.exit(1)

    entry = entries[0]
    name = entry["名前"]
    prompt = entry.get("portrait_prompt", "")
    era = entry.get("era", "")

    print(f"生成対象: {name} ({era})")
    print(f"プロンプト (先頭100文字): {prompt[:100]}...")

    output_path = get_output_path(entry["id"], output_dir)
    print(f"保存先: {output_path}")

    print("画像を生成中...")
    image_data = generate_image(api_client, prompt)
    save_image(output_path, image_data)
    print(f"完了: {output_path} ({len(image_data):,} bytes)")


if __name__ == "__main__":
    main()
