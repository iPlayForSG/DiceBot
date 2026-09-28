"""Shared, server-authoritative tabletop for the newly imported workshop games.

Rules are resolved by the players. The service owns card order, private hands,
the public table and scores so a QQ group can play over a persistent room.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import Counter
import json
from pathlib import Path
import random
import time

from tabletop_server.engine import GameError, Player


NAMES = {"love-letter": "情书", "once-upon-a-time": "从前从前", "sushi-go": "寿司 Go！",
         "azul": "花砖物语", "flip-city": "翻转城市", "hanamikoji": "花见小路"}
LIMITS = {"love-letter": (2, 6), "once-upon-a-time": (2, 6), "sushi-go": (2, 5),
          "azul": (2, 4), "flip-city": (2, 4), "hanamikoji": (2, 2)}
ASSETS = Path(__file__).resolve().parents[1] / "web/public/assets"


def _catalog(slug: str) -> tuple[dict[str, dict], list[str], list[str]]:
    if slug == "sushi-go":
        pack = json.loads((ASSETS / slug / "cards.json").read_text(encoding="utf-8"))
        return {c["id"]: c for c in pack}, [c["id"] for c in pack], []
    manifest = json.loads((ASSETS / slug / "manifest.json").read_text(encoding="utf-8"))
    source = json.loads((ASSETS / slug / "tts-source.json").read_text(encoding="utf-8")) if slug == "once-upon-a-time" else None
    cards, main, ending = {}, [], []
    by_path = {obj["path"]: obj for obj in manifest["objects"]}
    for index, obj in enumerate(manifest["objects"]):
        if obj["type"] != "Card" or not obj["image"]:
            continue
        if slug == "flip-city" and "/States/" in obj["path"]:
            continue
        if slug == "love-letter" and obj["card_id"] // 100 != 5:
            continue
        if slug == "hanamikoji" and obj["card_id"] // 100 != 1:
            continue
        if slug == "once-upon-a-time":
            root_index = int(obj["path"].split("/")[1])
            group = "ending" if "结局牌" in source["ObjectStates"][root_index].get("Description", "") else "story"
        else:
            group = "story"
        card_id = f"c{index}"
        cards[card_id] = {"id": card_id, "image": f"public/assets/{slug}/{obj['image']}",
                          "name": obj["name"] or f"卡牌 {index+1}", "group": group,
                          "card_id": obj["card_id"]}
        if slug == "flip-city":
            alternate = by_path.get(obj["path"] + "/States/2")
            if alternate and alternate["image"]:
                cards[card_id]["alternate_image"] = f"public/assets/{slug}/{alternate['image']}"
            cards[card_id]["root"] = int(obj["path"].split("/")[1])
        (ending if group == "ending" else main).append(card_id)
    return cards, main, ending


CATALOGS = {slug: _catalog(slug) for slug in NAMES}


@dataclass
class WorkshopRoom:
    code: str
    group_id: str
    players: list[Player]
    game: str
    mode: str = "basic"
    phase: str = "lobby"
    state: dict = field(default_factory=dict)
    log: list[str] = field(default_factory=list)
    revision: int = 0
    created_at: float = field(default_factory=time.time)

    def player(self, qq_id: str) -> Player:
        for player in self.players:
            if player.qq_id == qq_id:
                return player
        raise GameError("你不在本房间。")

    def _record(self, message: str) -> None:
        self.log.append(message)
        self.log = self.log[-40:]
        self.revision += 1

    def add_player(self, qq_id: str, name: str) -> None:
        if self.phase != "lobby":
            raise GameError("游戏已经开始。")
        if any(p.qq_id == qq_id for p in self.players):
            raise GameError("你已经加入。")
        if len(self.players) >= LIMITS[self.game][1]:
            raise GameError(f"本游戏最多 {LIMITS[self.game][1]} 人。")
        self.players.append(Player(qq_id, name[:24]))
        self._record(f"{name[:24]} 加入房间。")

    def start(self) -> None:
        if self.phase != "lobby":
            raise GameError("游戏已经开始。")
        low, high = LIMITS[self.game]
        if not low <= len(self.players) <= high:
            raise GameError(f"需要 {low}–{high} 人。")
        _, base, endings = CATALOGS[self.game]
        deck, ending_deck = base.copy(), endings.copy()
        random.SystemRandom().shuffle(deck)
        random.SystemRandom().shuffle(ending_deck)
        hands = {p.qq_id: [] for p in self.players}
        table = {p.qq_id: [] for p in self.players}
        if self.game == "love-letter":
            deck.pop()  # Private set-aside card.
            if len(self.players) == 2:
                for _ in range(3): deck.pop()
            for p in self.players: hands[p.qq_id].append(deck.pop())
        elif self.game == "once-upon-a-time":
            n = {2: 10, 3: 8, 4: 7, 5: 6, 6: 5}[len(self.players)]
            for p in self.players:
                hands[p.qq_id] = [deck.pop() for _ in range(n)] + [ending_deck.pop()]
        elif self.game == "sushi-go":
            n = {2: 10, 3: 9, 4: 8, 5: 7}[len(self.players)]
            for p in self.players: hands[p.qq_id] = [deck.pop() for _ in range(n)]
        elif self.game == "hanamikoji":
            deck.pop()  # Secretly removed gift.
            for p in self.players: hands[p.qq_id] = [deck.pop() for _ in range(6)]
        elif self.game == "flip-city":
            catalog = CATALOGS[self.game][0]
            starters = [[c for c in base if catalog[c]["root"] == root] for root in (10, 11, 12)]
            starters += [[c for c in base if catalog[c]["root"] == 0][i:i + 9] for i in (0, 9, 18)]
            self.state = {"personal_decks": {}, "personal_discard": {}, "market": [c for c in base if catalog[c]["root"] in {5, 6, 7, 8, 9}], "flipped": []}
            for p, starter in zip(self.players, starters):
                random.SystemRandom().shuffle(starter)
                self.state["personal_decks"][p.qq_id] = starter
                self.state["personal_discard"][p.qq_id] = []
            deck = []
        self.state.update({"deck": deck, "ending_deck": ending_deck, "hands": hands, "table": table,
                      "discard": [], "current": 0, "round": 1,
                      "scores": {p.qq_id: 0 for p in self.players}, "chosen": {},
                      "saved_puddings": {p.qq_id: [] for p in self.players}})
        if self.game == "azul":
            self.state["tiles"] = {color: 20 for color in "wugrb"}
            self.state["factories"] = []
            self._fill_factories()
        self.phase = "playing"
        self._record(f"{NAMES[self.game]}开局。请打开规则书，按牌面与规则协商结算。")

    def _fill_factories(self) -> None:
        bag = [c for c, n in self.state["tiles"].items() for _ in range(n)]
        random.SystemRandom().shuffle(bag)
        count = 2 * len(self.players) + 1
        self.state["factories"] = [bag[i * 4:(i + 1) * 4] for i in range(count)]
        self.state["center"] = []
        self.state["tiles"] = {c: bag[count * 4:].count(c) for c in "wugrb"}

    def _require_turn(self, player: Player) -> None:
        if self.state["current"] != self.players.index(player):
            raise GameError("现在不是你的回合。")

    def _card(self, card_id: str) -> dict:
        card = CATALOGS[self.game][0].get(card_id)
        if not card:
            raise GameError("无效卡牌。")
        return card

    def action(self, qq_id: str, action: dict) -> None:
        if self.phase != "playing":
            raise GameError("游戏尚未开始或已结束。")
        player = self.player(qq_id)
        kind = action.get("type")
        hands, table = self.state["hands"], self.state["table"]
        card_id = str(action.get("card_id") or "")
        if kind in {"draw", "play", "discard", "pass", "turn", "tile"}:
            self._require_turn(player)
        if kind == "pick" and self.game == "sushi-go":
            if qq_id in self.state["chosen"]:
                raise GameError("请等待其他玩家选牌。")
            if card_id not in hands[qq_id]:
                raise GameError("请选择自己手中的寿司牌。")
            hands[qq_id].remove(card_id)
            self.state["chosen"][qq_id] = card_id
            self._record(f"{player.name} 已暗选一张牌。")
            if len(self.state["chosen"]) == len(self.players):
                for p in self.players:
                    table[p.qq_id].append(self.state["chosen"][p.qq_id])
                rotated = [hands[p.qq_id] for p in self.players]
                for index, p in enumerate(self.players):
                    hands[p.qq_id] = rotated[(index - 1) % len(self.players)]
                self.state["chosen"] = {}
                self._record("所有玩家亮牌，剩余手牌传给左侧玩家。")
        elif kind == "draw":
            if self.game == "flip-city":
                pile = self.state["personal_decks"][qq_id]
                if not pile:
                    pile.extend(self.state["personal_discard"][qq_id])
                    self.state["personal_discard"][qq_id] = []
                    random.SystemRandom().shuffle(pile)
                if not pile:
                    raise GameError("个人牌堆与弃牌堆都已空。")
                table[qq_id].append(pile.pop())
                self._record(f"{player.name} 翻开了 1 张城市卡。")
                return
            pile = self.state["ending_deck"] if action.get("pile") == "ending" else self.state["deck"]
            if not pile:
                raise GameError("牌堆已空。")
            hands[qq_id].append(pile.pop())
            self._record(f"{player.name} 抽了 1 张牌。")
        elif kind in {"play", "discard", "pass"}:
            if card_id not in hands[qq_id]:
                raise GameError("这张牌不在你的手中。")
            hands[qq_id].remove(card_id)
            if kind == "play":
                table[qq_id].append(card_id)
                self._record(f"{player.name} 打出了 {self._card(card_id)['name']}。")
            elif kind == "discard":
                self.state["discard"].append(card_id)
                self._record(f"{player.name} 弃掉 1 张牌。")
            else:
                target = str(action.get("target") or "")
                if target not in hands or target == qq_id:
                    raise GameError("请选择其他玩家。")
                hands[target].append(card_id)
                self._record(f"{player.name} 向另一玩家传出 1 张牌。")
        elif kind == "turn":
            if self.game == "flip-city":
                self.state["personal_discard"][qq_id].extend(table[qq_id])
                table[qq_id] = []
            for step in range(1, len(self.players) + 1):
                candidate = (self.state["current"] + step) % len(self.players)
                if self.players[candidate].alive:
                    self.state["current"] = candidate
                    break
            self._record(f"轮到 {self.players[self.state['current']].name}。")
        elif kind in {"buy", "develop"} and self.game == "flip-city":
            self._require_turn(player)
            market = self.state["market"]
            if card_id not in market:
                raise GameError("公共供应堆已无此卡。")
            market.remove(card_id)
            self.state["personal_discard"][qq_id].append(card_id)
            if kind == "develop":
                if "alternate_image" not in self._card(card_id):
                    raise GameError("这张卡不能翻面开发。")
                self.state["flipped"].append(card_id)
            self._record(f"{player.name} {'直接开发' if kind == 'develop' else '购买'}了一张城市卡；费用请按牌面结算。")
        elif kind == "flip_card" and self.game == "flip-city":
            self._require_turn(player)
            if card_id not in self.state["personal_discard"][qq_id] or "alternate_image" not in self._card(card_id):
                raise GameError("只能翻转自己弃牌堆里的双面卡。")
            flips = self.state["flipped"]
            if card_id in flips: flips.remove(card_id)
            else: flips.append(card_id)
            self._record(f"{player.name} 翻转了一张弃牌堆里的卡；费用请按牌面结算。")
        elif kind == "eliminate" and self.game == "love-letter":
            self._require_turn(player)
            target = self.player(str(action.get("target") or ""))
            if target is player or not target.alive:
                raise GameError("请选择尚未出局的其他玩家。")
            target.alive = False
            self.state["discard"].extend(hands[target.qq_id])
            hands[target.qq_id] = []
            self._record(f"{target.name} 本轮出局。")
        elif kind == "interrupt" and self.game == "once-upon-a-time":
            if self.state["current"] == self.players.index(player) or card_id not in hands[qq_id]:
                raise GameError("请用手中的故事牌打断当前讲述者。")
            if self._card(card_id)["group"] == "ending":
                raise GameError("结局牌不能用于打断。")
            previous = self.players[self.state["current"]]
            hands[qq_id].remove(card_id)
            table[qq_id].append(card_id)
            if self.state["deck"]:
                hands[previous.qq_id].append(self.state["deck"].pop())
            self.state["current"] = self.players.index(player)
            self._record(f"{player.name} 打断了 {previous.name}，并接续讲述。")
        elif kind == "declare_win" and self.game == "once-upon-a-time":
            self._require_turn(player)
            remaining = [c for c in hands[qq_id] if self._card(c)["group"] != "ending"]
            if remaining:
                raise GameError("请先打完所有故事牌。")
            ending = next((c for c in hands[qq_id] if self._card(c)["group"] == "ending"), None)
            if not ending:
                raise GameError("你没有结局牌。")
            hands[qq_id].remove(ending)
            table[qq_id].append(ending)
            self.phase = "finished"
            self._record(f"{player.name} 打出结局牌，完成故事。")
        elif kind == "score":
            target = str(action.get("target") or qq_id)
            if target not in self.state["scores"]:
                raise GameError("玩家不存在。")
            delta = int(action.get("delta") or 0)
            if not -100 <= delta <= 100:
                raise GameError("单次分数调整应在 ±100 内。")
            self.state["scores"][target] += delta
            self._record(f"{player.name} 将 {self.player(target).name} 的分数调整 {delta:+d}。")
        elif kind == "tile" and self.game == "azul":
            source = int(action.get("source", -1))
            color = str(action.get("color") or "")
            if color not in "wugrb" or source < -1 or source >= len(self.state["factories"]):
                raise GameError("请选择有效工厂和颜色。")
            if source == -1:
                zone = self.state["center"]
            else:
                zone = self.state["factories"][source]
            taken = zone.count(color)
            if not taken:
                raise GameError("该处没有这种颜色。")
            zone[:] = [c for c in zone if c != color]
            if source >= 0:
                self.state["center"].extend(zone)
                zone.clear()
            self.state.setdefault("player_tiles", {p.qq_id: [] for p in self.players})[qq_id].extend([color] * taken)
            self._record(f"{player.name} 拿取了 {taken} 块花砖。")
            self.state["current"] = (self.state["current"] + 1) % len(self.players)
        elif kind == "place_tile" and self.game == "azul":
            color = str(action.get("color") or "")
            row = int(action.get("row", -1))
            if color not in "wugrb" or row not in range(5):
                raise GameError("请选择花砖颜色和图板行。")
            tiles = self.state.setdefault("player_tiles", {p.qq_id: [] for p in self.players})[qq_id]
            if color not in tiles:
                raise GameError("你尚未取得这块花砖。")
            pattern = self.state.setdefault("pattern", {p.qq_id: [[] for _ in range(5)] for p in self.players})[qq_id]
            if len(pattern[row]) >= row + 1 or (pattern[row] and pattern[row][0] != color):
                raise GameError("本行已满或颜色不一致。")
            tiles.remove(color)
            pattern[row].append(color)
            self._record(f"{player.name} 把一块花砖放在第 {row + 1} 行。")
        elif kind == "resolve_pattern" and self.game == "azul":
            row = int(action.get("row", -1))
            if row not in range(5):
                raise GameError("请选择图板行。")
            pattern = self.state.setdefault("pattern", {p.qq_id: [[] for _ in range(5)] for p in self.players})[qq_id]
            if len(pattern[row]) != row + 1:
                raise GameError("该图板行尚未填满。")
            color = pattern[row][0]
            pattern[row] = []
            self.state.setdefault("wall", {p.qq_id: [] for p in self.players})[qq_id].append(color)
            self._record(f"{player.name} 把第 {row + 1} 行的花砖移到墙面；请按规则计分。")
        elif kind == "next_round":
            if self.players[0] is not player:
                raise GameError("只有房主可以开启下一轮。")
            self.state["round"] += 1
            if self.game == "sushi-go":
                if self.state["round"] > 3:
                    self.state["round"] -= 1
                    raise GameError("三轮已结束，请结算布丁与总分。")
                if any(hands[p.qq_id] for p in self.players) or self.state["chosen"]:
                    self.state["round"] -= 1
                    raise GameError("请等待本轮所有手牌完成选择。")
                n = {2: 10, 3: 9, 4: 8, 5: 7}[len(self.players)]
                for p in self.players:
                    self.state["saved_puddings"][p.qq_id].extend(
                        c for c in table[p.qq_id] if self._card(c)["name"] == "布丁")
                    self.state["discard"].extend(
                        c for c in table[p.qq_id] if self._card(c)["name"] != "布丁")
                    hands[p.qq_id] = [self.state["deck"].pop() for _ in range(n)]
                    table[p.qq_id] = []
                self.state["chosen"] = {}
            elif self.game == "azul":
                if not any(self.state["tiles"].values()):
                    self.state["tiles"] = {c: 20 for c in "wugrb"}
                self._fill_factories()
            elif self.game == "love-letter":
                for p in self.players: p.alive = True
                self.state["deck"] = CATALOGS[self.game][1].copy()
                random.SystemRandom().shuffle(self.state["deck"])
                self.state["deck"].pop()
                for p in self.players:
                    hands[p.qq_id] = [self.state["deck"].pop()]
                    table[p.qq_id] = []
            elif self.game == "hanamikoji":
                self.state["deck"] = CATALOGS[self.game][1].copy()
                random.SystemRandom().shuffle(self.state["deck"])
                self.state["deck"].pop()
                for p in self.players:
                    hands[p.qq_id] = [self.state["deck"].pop() for _ in range(6)]
                    table[p.qq_id] = []
            else:
                raise GameError("本游戏没有自动下一轮功能。")
            self._record(f"第 {self.state['round']} 轮开始。")
        elif kind == "finish":
            if self.players[0] is not player:
                raise GameError("只有房主可以结束。")
            self.phase = "finished"
            self._record("房主宣布本局结束。")
        else:
            raise GameError("未知行动。")

    def view(self, qq_id: str | None = None) -> dict:
        current = self.players[self.state.get("current", 0)].qq_id if self.state else None
        cards = CATALOGS[self.game][0]
        hands = self.state.get("hands", {})
        table = self.state.get("table", {})
        flipped = set(self.state.get("flipped", []))
        def visible(card_id: str) -> dict:
            card = cards[card_id].copy()
            if card_id in flipped:
                card["image"] = card.get("alternate_image", card["image"])
            return card
        market_counts = Counter(cards[c]["card_id"] for c in self.state.get("market", []))
        market = [{"card": visible(next(c for c in self.state["market"] if cards[c]["card_id"] == key)),
                   "count": count} for key, count in market_counts.items()]
        return {"code": self.code, "game": self.game, "mode": self.mode, "phase": self.phase,
                "createdAt": int(self.created_at), "expiresAt": int(self.created_at + 300) if self.phase == "lobby" else None,
                "revision": self.revision, "current": current, "round": self.state.get("round", 1),
                "players": [{"id": p.qq_id, "name": p.name, "avatar": p.avatar, "alive": p.alive,
                             "claimed": bool(p.token), "cards": len(hands.get(p.qq_id, [])),
                             "score": self.state.get("scores", {}).get(p.qq_id, 0),
                             "puddings": len(self.state.get("saved_puddings", {}).get(p.qq_id, [])) +
                                         sum(self._card(c)["name"] == "布丁" for c in table.get(p.qq_id, [])) if self.game == "sushi-go" else 0,
                             "pattern": self.state.get("pattern", {}).get(p.qq_id, [[] for _ in range(5)]) if self.game == "azul" else [],
                             "wall": self.state.get("wall", {}).get(p.qq_id, []) if self.game == "azul" else [],
                             "tiles": self.state.get("player_tiles", {}).get(p.qq_id, []) if self.game == "azul" else [],
                             "table": [visible(c) for c in table.get(p.qq_id, [])]} for p in self.players],
                "me": ({"id": qq_id, "hand": [visible(c) for c in hands.get(qq_id, [])],
                        "discard": [visible(c) for c in self.state.get("personal_discard", {}).get(qq_id, [])]} if qq_id else None),
                "deckCount": (len(self.state.get("personal_decks", {}).get(qq_id, [])) if self.game == "flip-city" and qq_id else len(self.state.get("deck", []))),
                "discardCount": (len(self.state.get("personal_discard", {}).get(qq_id, [])) if self.game == "flip-city" and qq_id else len(self.state.get("discard", []))),
                "discardCards": [visible(c) for c in self.state.get("discard", [])[-30:]],
                "market": market,
                "factories": self.state.get("factories", []), "center": self.state.get("center", []),
                "myTiles": self.state.get("player_tiles", {}).get(qq_id, []) if qq_id else [],
                "myPattern": self.state.get("pattern", {}).get(qq_id, [[] for _ in range(5)]) if qq_id else [],
                "myWall": self.state.get("wall", {}).get(qq_id, []) if qq_id else [],
                "picked": qq_id in self.state.get("chosen", {}) if qq_id else False,
                "pickedCount": len(self.state.get("chosen", {})),
                "log": self.log[-25:]}
