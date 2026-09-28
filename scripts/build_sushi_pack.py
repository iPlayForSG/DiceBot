"""Repair a vanished Chinese Sushi Go sheet with locally stored TTS artwork.

The Chinese workshop save supplies the base-game deck counts and rule image.
Artwork comes from the still-available Sushi Go Party workshop item 780801567.
"""

import json
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
source = root / "data/alt-assets/sushi-alt/cards"
target = root / "web/public/assets/sushi-go/cards"
target.mkdir(parents=True, exist_ok=True)
types = [
    ("天妇罗", 14, "deck-1-31.webp"), ("生鱼片", 14, "deck-1-23.webp"),
    ("饺子", 14, "deck-1-01.webp"), ("寿司卷 2", 12, "deck-1-13.webp"),
    ("寿司卷 3", 8, "deck-1-14.webp"), ("寿司卷 1", 6, "deck-1-12.webp"),
    ("鲑鱼握寿司", 10, "deck-1-22.webp"), ("鱿鱼握寿司", 5, "deck-1-27.webp"),
    ("鸡蛋握寿司", 5, "deck-1-04.webp"), ("布丁", 10, "deck-1-21.webp"),
    ("芥末", 6, "deck-1-36.webp"), ("筷子", 4, "deck-1-00.webp"),
]
cards = []
for name, count, filename in types:
    shutil.copyfile(source / filename, target / filename)
    for i in range(count):
        cards.append({"id": f"s{len(cards)}", "name": name,
                      "image": f"public/assets/sushi-go/cards/{filename}", "group": "story"})
assert len(cards) == 108
(target.parent / "cards.json").write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")
(target.parent / "card-art-source.json").write_text(json.dumps({
    "base_game_save": "https://steamcommunity.com/sharedfiles/filedetails/?id=776875059",
    "replacement_art_save": "https://steamcommunity.com/sharedfiles/filedetails/?id=780801567",
    "reason": "The base game's Chinese face sheet now returns HTTP 404; images are hosted locally and labeled in Chinese in the site.",
}, ensure_ascii=False, indent=2), encoding="utf-8")
print("sushi-go", len(cards), "cards", len(types), "local images")
