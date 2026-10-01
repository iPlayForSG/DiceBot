"""Create isolated fake-player rooms for browser verification; never touch production rooms."""

from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tabletop_server.engine import GameRoom, Player, CARDS
from tabletop_server.party_games import PartyRoom, LIMITS as PARTY_LIMITS, bird, SPLENDOR_CARDS
from tabletop_server.workshop_room import WorkshopRoom, LIMITS as WORKSHOP_LIMITS


def build():
    art = json.loads((ROOT / "web/public/assets/table-art.json").read_text(encoding="utf-8"))
    variants = [("exploding-kittens", "basic"), *[(g, "basic") for g in PARTY_LIMITS],
                *[(g, "basic") for g in WORKSHOP_LIMITS],
                ("coup", "reformation"), ("coup", "ks-bureaucrat"), ("coup", "ks-speculator")]
    rooms, fixtures = [], []
    for index, (game, mode) in enumerate(variants):
        count = PARTY_LIMITS.get(game, WORKSHOP_LIMITS.get(game, (2,5)))[0]
        players = [Player(str(10001+i), f"测试玩家{i+1}", token=f"fixture-{index}-{i}", claim_code=f"CLAIM{i+1:05}") for i in range(count)]
        code = f"VIEW{index:04}"
        room = (GameRoom(code, code, players, mode=mode) if game=="exploding-kittens" else
                PartyRoom(code, code, players, game, mode=mode) if game in PARTY_LIMITS else
                WorkshopRoom(code, code, players, game, mode=mode))
        room.start()
        first = players[0].qq_id
        if game == "splendor":
            room.action(first, {"type":"reserve", "card":room.state["market"]["1"][0], "tier":1})
        elif game in {"love-letter", "once-upon-a-time", "hanamikoji"}:
            if game != "once-upon-a-time": room.action(first, {"type":"draw"})
            card = next(c for c in room.state["hands"][first] if room._card(c)["group"] != "ending")
            room.action(first, {"type":"play", "card_id":card})
        elif game == "sushi-go":
            for p in players: room.action(p.qq_id, {"type":"pick", "card_id":room.state["hands"][p.qq_id][0]})
        elif game == "flip-city": room.action(first, {"type":"draw"})
        elif game == "azul":
            for i,p in enumerate(players):
                color=room.state["factories"][i][0]
                room.action(p.qq_id,{"type":"tile","source":i,"color":color})
        elif game == "coup":
            lost = players[1].hand.pop()
            room.state["lost"][players[1].qq_id].append(lost)
        def private_images(player):
            v=room.view(player.qq_id)
            if game=="exploding-kittens": return ["public/assets/exploding-kittens/"+CARDS[c]["image"] for c in v["me"]["hand"]]
            if game=="coup": return [art[game]["roles"][c] for c in v["me"]["hand"]]
            if game=="cubirds": return [bird(c)["image"] for c in v["me"]["hand"]]
            if game=="splendor": return [SPLENDOR_CARDS[c]["image"] for c in v["state"]["reserved"][player.qq_id]]
            if game=="avalon": return [v["me"]["roleImage"]]
            if game=="azul": return [art[game]["tiles"][c] for c in v["myTiles"]]
            if game=="flip-city":
                p=next(p for p in v["players"] if p["id"]==player.qq_id)
                return ([p["deckTop"]["image"]] if p["deckTop"] else [])+[c["image"] for c in p["table"]]
            return [c["image"] for c in v["me"]["hand"]]
        rooms.append(asdict(room))
        fixtures.append({"game":game,"mode":mode,"code":code,
                         "players":[{"id":p.qq_id,"token":p.token,"claim":p.claim_code,"privateImages":private_images(p)} for p in players]})
    destination = ROOT / "data/player-view-verification"
    destination.mkdir(parents=True,exist_ok=True)
    (destination / "rooms.json").write_text(json.dumps(rooms,ensure_ascii=False),encoding="utf-8")
    (destination / "fixtures.json").write_text(json.dumps(fixtures,ensure_ascii=False),encoding="utf-8")
    print("Created",len(fixtures),"isolated rooms and",sum(len(f["players"]) for f in fixtures),"fake player views")


if __name__ == "__main__": build()
