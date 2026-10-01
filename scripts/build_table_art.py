"""Index and crop locally imported workshop art for the public and private tables."""

from pathlib import Path
import json
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "web/public/assets"


def manifest(slug):
    return json.loads((ASSETS / slug / "manifest.json").read_text(encoding="utf-8"))


def path(slug, image):
    return f"public/assets/{slug}/{image}" if image else None


def crop(slug, image, target, fractions):
    with Image.open(ASSETS / slug / image) as source:
        box = tuple(round(f * (source.width if i % 2 == 0 else source.height)) for i, f in enumerate(fractions))
        result = source.crop(box)
        destination = ASSETS / slug / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        result.save(destination, "WEBP", quality=90)
    return path(slug, target)


def build():
    data = {}
    for slug, deck in {"coup":"3", "cubirds":"1", "splendor":"5", "avalon":"3",
                       "love-letter":"5", "once-upon-a-time":"8", "flip-city":"1", "hanamikoji":"1"}.items():
        m = manifest(slug)
        data[slug] = {"back":path(slug, m["decks"][deck]["back"])}
    data["exploding-kittens"] = {"back":"public/assets/exploding-kittens/card-back.jpg"}
    sushi = manifest("sushi-go")
    source = json.loads((ASSETS / "sushi-go/tts-source.json").read_text(encoding="utf-8"))
    back_url = next((spec.get("BackURL") for obj in source["ObjectStates"] for spec in (obj.get("CustomDeck") or {}).values()), None)
    data["sushi-go"] = {"back":path("sushi-go", sushi["images"].get(back_url))}

    data["coup"]["roles"] = {name:f"public/assets/coup/cards/deck-3-{index:02}.webp" for name,index in
                                {"公爵":0,"上尉":1,"刺客":2,"女爵":3,"大使":4,"判官":5,"弄臣":6,"投机者":7,"官僚":8}.items()}
    data["coup"]["factions"] = {"改革":"public/assets/coup/cards/deck-4-00.webp",
        "秩序":crop("coup", "images/716bf1e940f4a978.webp", "table/faction-order.webp", (0,0,.25,.2))}
    data["coup"]["coin"] = crop("coup", "images/cb0aaa7854828faa.webp", "table/coin.webp", (0,.70,.303,1))
    # TTS reuses deck ID 9 for several unrelated objects; use this object's own texture.
    data["coup"]["treasury"] = "public/assets/coup/images/b6711f4deffbeb37.webp"

    avalon = manifest("avalon")
    data["avalon"]["choices"] = {kind:path("avalon", next(o["image"] for o in avalon["objects"] if o["type"]=="Card" and o["description"]==kind))
                                    for kind in ("success","fail","approve","reject")}
    data["avalon"]["roles"] = {o["description"]:path("avalon",o["image"]) for o in avalon["objects"] if o["type"]=="Card" and o["description"]}
    data["splendor"]["gems"] = {color:crop("splendor", image, f"table/gem-{color}.webp", (0,0,.5,1)) for color,image in zip("wugrbj",
        ["images/742a50d337adbafe.webp","images/88a7a6b17464cbed.webp","images/4d6aa147f9092289.webp",
         "images/6979b24619e9d667.webp","images/689ad2f57e5f0e79.webp","images/07544755cc837a96.webp"])}
    data["azul"] = {"board":"public/assets/azul/images/f6b7379c5a970766.webp", "tiles":dict(zip("wugrb",[
        "public/assets/azul/images/21841d35927e0353.webp", "public/assets/azul/images/2f8a9935ae0f42cf.webp",
        "public/assets/azul/images/634e9aebb0b19bb5.webp", "public/assets/azul/images/7650f2fce901cb6e.webp",
        "public/assets/azul/images/ef00c97043bbfda2.webp"]))}
    hana = manifest("hanamikoji")
    data["hanamikoji"]["geishas"] = [{"name":o["name"],"image":path("hanamikoji",o["custom_image"])} for o in hana["objects"] if o["type"]=="Custom_Tile" and "※" in o["name"]]
    data["hanamikoji"]["actions"] = {o["name"]:path("hanamikoji",o["custom_image"]) for o in hana["objects"] if o["type"]=="Custom_Tile" and o["name"] in {"密约","取舍","赠予","竞争"}}

    def verify(value):
        if isinstance(value, str) and value.startswith("public/assets/"):
            assert (ROOT / "web" / value).is_file(), value
        elif isinstance(value, dict):
            for item in value.values(): verify(item)
        elif isinstance(value, list):
            for item in value: verify(item)
    verify(data)
    (ASSETS / "table-art.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Indexed local tabletop art for",len(data),"games")


if __name__ == "__main__":
    build()
