"""Import the exact TTS workshop save and keep all card art in this project.

Usage: uv run python scripts/import_tts.py PATH_TO_2375784308.json
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
from urllib.request import Request, urlopen

from PIL import Image


KIND_BY_FACE = {
    **{i: "bomb" for i in (0, 1, 2, 40)},
    **{i: "attack" for i in (3, 32, 33, 38)},
    **{i: "cat" for i in (4, 5, 6, 7, 8)},
    **{i: "see" for i in (9, 10, 11, 12, 14)},
    **{i: "shuffle" for i in (13, 15, 16, 17)},
    **{i: "nope" for i in (18, 19, 20, 21, 22)},
    **{i: "favor" for i in (23, 24, 25, 39)},
    **{i: "defuse" for i in (26, 27, 28, 29, 30, 31)},
    **{i: "skip" for i in (34, 35, 36, 37)},
}


def download(url: str) -> bytes:
    # TTS keeps older cloud-* links. The current image CDN serves the same UGC id.
    if "/ugc/" not in url or "steamusercontent.com" not in url:
        raise ValueError(f"Unexpected asset URL: {url}")
    current = "https://images.steamusercontent.com/ugc/" + url.split("/ugc/", 1)[1]
    with urlopen(Request(current, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as response:
        return response.read()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path("web/public/assets/exploding-kittens"))
    args = parser.parse_args()
    data = json.loads(args.source.read_text(encoding="utf-8-sig"))
    if data.get("SaveName") != "炸弹猫（个人精翻版）":
        raise ValueError("This is not the requested workshop save")
    deck = next(obj["CustomDeck"]["2"] for obj in data["ObjectStates"] if obj.get("CustomDeck"))
    card_ids = [id_ for obj in data["ObjectStates"] for id_ in obj.get("DeckIDs", [])]
    if len(card_ids) != 56 or set(KIND_BY_FACE) != set(range(41)):
        raise ValueError("The workshop deck differs from the mapped 56-card version")
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    (out / "card-sheet.jpg").write_bytes(download(deck["FaceURL"]))
    (out / "card-back.jpg").write_bytes(download(deck["BackURL"]))
    shutil.copy2(args.source, out / "tts-source.json")
    sheet = Image.open(out / "card-sheet.jpg")
    for index in range(41):
        column, row = index % 10, index // 10
        box = tuple(round(value) for value in (
            column * sheet.width / 10, row * sheet.height / 7,
            (column + 1) * sheet.width / 10, (row + 1) * sheet.height / 7,
        ))
        sheet.crop(box).save(out / f"card-{index:02}.jpg", quality=90, optimize=True)
    manifest = {
        "workshop": "https://steamcommunity.com/sharedfiles/filedetails/?id=2375784308",
        "creator": "ChopDaSushi",
        "source_image_urls": deck,
        "cards": [
            {"id": f"c{number:02}", "face": card_id % 100,
             "kind": KIND_BY_FACE[card_id % 100], "image": f"card-{card_id % 100:02}.jpg"}
            for number, card_id in enumerate(card_ids)
        ],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Imported", len(card_ids), "cards:", Counter(card["kind"] for card in manifest["cards"]))


if __name__ == "__main__":
    main()
