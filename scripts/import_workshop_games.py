"""Download four TTS workshop saves and materialize their image assets locally.

Workshop payloads are BSON. The normalized manifests keep object/card metadata
for later rules work, while the website uses only files in web/public/assets.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from io import BytesIO
import json
from pathlib import Path
import time
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from bson import BSON
from PIL import Image


GAMES = {
    "cubirds": ("2299292104", "方·鸟 CuBirds（中文 Chinese）"),
    "coup": ("2385450244", "政变（简中）带扩展"),
    "splendor": ("2093855539", "璀璨宝石（Splendor）"),
    "avalon": ("929329226", "阿瓦隆 脚本汉化版"),
}
IMAGE_KEYS = {"FaceURL", "BackURL", "ImageURL", "DiffuseURL", "NormalURL"}


def fetch(url: str) -> bytes:
    host = urlparse(url).hostname or ""
    if host.endswith("steamusercontent.com") and "/ugc/" in url:
        url = "https://images.steamusercontent.com/ugc/" + url.split("/ugc/", 1)[1]
    elif host == "i.imgur.com":
        url = url.replace("http://", "https://", 1)
    else:
        raise ValueError(f"Unapproved image host: {host}")
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=45) as response:
                return response.read()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def workshop_save(workshop_id: str, slug: str) -> dict:
    cached = Path("data/workshop-sources") / f"{slug}.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    data = urlencode({"itemcount": 1, "publishedfileids[0]": workshop_id}).encode()
    request = Request(
        "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/",
        data=data,
    )
    with urlopen(request, timeout=30) as response:
        detail = json.load(response)["response"]["publishedfiledetails"][0]
    if detail.get("result") != 1 or detail.get("publishedfileid") != workshop_id:
        raise ValueError(f"Workshop item {workshop_id} unavailable")
    with urlopen(Request(detail["file_url"], headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as response:
        source = BSON(response.read()).decode()
    source.pop("DrawImage", None)  # Embedded thumbnail; not part of the table.
    return source


def objects(source: dict):
    def visit(value, path):
        if isinstance(value, dict):
            if "Name" in value and "Transform" in value:
                yield path, value
            for key, child in value.items():
                if isinstance(child, (dict, list)):
                    yield from visit(child, f"{path}/{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                yield from visit(child, f"{path}/{index}")

    yield from visit(source.get("ObjectStates", []), "ObjectStates")


def image_urls(source: dict) -> set[str]:
    found = set()

    def visit(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in IMAGE_KEYS and isinstance(child, str) and child.startswith("http"):
                    found.add(child)
                elif isinstance(child, (dict, list)):
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(source)
    return found


def store_images(urls: set[str], destination: Path, cache: Path) -> tuple[dict[str, str], dict[str, Path]]:
    destination.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    result = {}
    originals = {}

    def one(url: str) -> tuple[str, str, Path]:
        digest = hashlib.sha256(url.encode()).hexdigest()[:16]
        source = cache / f"{digest}.bin"
        if not source.exists():
            legacy = next((p for p in destination.glob(f"{digest}.*") if p.suffix != ".webp"), None)
            source.write_bytes(legacy.read_bytes() if legacy else fetch(url))
        raw = source.read_bytes()
        with Image.open(BytesIO(raw)) as image:
            image.verify()
        filename = digest + ".webp"
        target = destination / filename
        if target.exists():
            return url, f"images/{filename}", source
        with Image.open(BytesIO(raw)) as image:
            image.thumbnail((2200, 2200))
            image.convert("RGB").save(target, "WEBP", quality=80, method=5)
        return url, f"images/{filename}", source

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(one, url): url for url in urls}
        for future in as_completed(futures):
            try:
                url, name, source = future.result()
                result[url] = name
                originals[url] = source
            except Exception as exc:
                print(f"Image unavailable: {futures[future]} ({exc})")
    return result, originals


def crop_card_sheets(source: dict, out: Path, local: dict[str, str], originals: dict[str, Path]) -> dict[str, dict]:
    decks = {}
    used: dict[str, set[int]] = {}
    for _, obj in objects(source):
        for deck_id, spec in obj.get("CustomDeck", {}).items():
            current = decks.get(deck_id)
            capacity = int(spec["NumWidth"]) * int(spec["NumHeight"])
            if current is None or capacity > int(current["NumWidth"]) * int(current["NumHeight"]):
                decks[deck_id] = spec
        ids = list(obj.get("DeckIDs", []))
        if isinstance(obj.get("CardID"), int):
            ids.append(obj["CardID"])
        for card_id in ids:
            if isinstance(card_id, int):
                used.setdefault(str(card_id // 100), set()).add(card_id % 100)
    card_dir = out / "cards"
    card_dir.mkdir(exist_ok=True)
    manifest = {}
    for deck_id, spec in decks.items():
        face_url = spec.get("FaceURL", "")
        face_path = originals.get(face_url)
        if not face_path:
            print(f"Deck {deck_id} face image unavailable")
            continue
        width, height = int(spec["NumWidth"]), int(spec["NumHeight"])
        faces: list[str | None] = [None] * (width * height)
        with Image.open(face_path) as sheet:
            for index in sorted(used.get(deck_id, [])):
                if index >= width * height:
                    raise ValueError(f"Card index {index} exceeds deck {deck_id} sheet")
                filename = f"deck-{deck_id}-{index:02}.webp"
                box = tuple(round(value) for value in (
                    (index % width) * sheet.width / width,
                    (index // width) * sheet.height / height,
                    ((index % width) + 1) * sheet.width / width,
                    ((index // width) + 1) * sheet.height / height,
                ))
                sheet.crop(box).convert("RGB").save(card_dir / filename, "WEBP", quality=82, method=5)
                faces[index] = f"cards/{filename}"
        manifest[deck_id] = {
            "faces": faces,
            "back": local.get(spec.get("BackURL", "")),
            "width": width,
            "height": height,
        }
    return manifest


def import_game(slug: str, out_root: Path) -> None:
    workshop_id, title = GAMES[slug]
    out = out_root / slug
    out.mkdir(parents=True, exist_ok=True)
    source = workshop_save(workshop_id, slug)
    (out / "tts-source.json").write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
    local, originals = store_images(image_urls(source), out / "images", Path("data/workshop-images") / slug)
    decks = crop_card_sheets(source, out, local, originals)
    obj_list = []
    for path, obj in objects(source):
        card_id = obj.get("CardID")
        obj_list.append({
            "path": path,
            "type": obj.get("Name"),
            "name": obj.get("Nickname", ""),
            "description": obj.get("Description", ""),
            "guid": obj.get("GUID", ""),
            "card_id": card_id,
            "image": decks.get(str(card_id // 100), {}).get("faces", [])[card_id % 100]
                if isinstance(card_id, int) and str(card_id // 100) in decks
                and card_id % 100 < len(decks[str(card_id // 100)]["faces"]) else None,
            "deck_ids": obj.get("DeckIDs", []),
            "custom_image": local.get(obj.get("CustomImage", {}).get("ImageURL", "")),
        })
    manifest = {
        "slug": slug,
        "name": title,
        "workshop": f"https://steamcommunity.com/sharedfiles/filedetails/?id={workshop_id}",
        "save_name": source.get("SaveName", ""),
        "images": local,
        "decks": decks,
        "objects": obj_list,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(slug, "images", len(local), "decks", len(decks), "objects", len(obj_list))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("games", nargs="*", choices=list(GAMES))
    parser.add_argument("--output", type=Path, default=Path("web/public/assets"))
    args = parser.parse_args()
    for slug in args.games or GAMES:
        import_game(slug, args.output)


if __name__ == "__main__":
    main()
