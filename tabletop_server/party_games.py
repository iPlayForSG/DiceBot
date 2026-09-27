"""Additional workshop games, with server-owned decks and private player views."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import json
from pathlib import Path
import random
import re

from tabletop_server.engine import GameError, Player


ASSETS = Path(__file__).resolve().parents[1] / "web/public/assets"
MANIFESTS = {
    slug: json.loads((ASSETS / slug / "manifest.json").read_text(encoding="utf-8"))
    for slug in ("cubirds", "coup", "splendor", "avalon")
}
LIMITS = {"cubirds": (2, 5), "coup": (2, 10), "splendor": (2, 4), "avalon": (5, 10)}
NAMES = {"cubirds": "方·鸟", "coup": "政变", "splendor": "璀璨宝石", "avalon": "阿瓦隆"}
COLORS = ("w", "u", "g", "r", "b")  # white, blue, green, red, black
GEM_NAMES = {"w": "白", "u": "蓝", "g": "绿", "r": "红", "b": "黑", "j": "黄金"}
BIRD_RANGES = {
    "1": [(0, 20, "长颈鸟", 6, 9), (20, 27, "火烈鸟", 2, 3),
          (27, 37, "巨嘴鸟", 3, 4), (37, 54, "喜鹊", 5, 7), (54, 64, "猫头鹰", 3, 4)],
    "2": [(0, 13, "红鸟", 4, 6), (13, 33, "黄鸟", 6, 9), (33, 46, "绿鸟", 4, 6)],
}
QUEST_SIZES = {
    5: (2, 3, 2, 3, 3), 6: (2, 3, 4, 3, 4), 7: (2, 3, 3, 4, 4),
    8: (3, 4, 4, 5, 5), 9: (3, 4, 4, 5, 5), 10: (3, 4, 4, 5, 5),
}
GOOD_COUNTS = {5: 3, 6: 4, 7: 4, 8: 5, 9: 6, 10: 6}
EVIL_ROLES = {"刺客", "莫甘娜", "莫德雷德", "奥伯伦", "爪牙"}
COUP_ROLES = {"公爵": 0, "上尉": 1, "刺客": 2, "女爵": 3, "大使": 4, "判官": 5,
              "官僚": 6, "投机者": 7, "弄臣": 8}


def bird(card: str) -> dict:
    deck, index = card[1:].split("-")
    number = int(index)
    for start, end, species, small, large in BIRD_RANGES[deck]:
        if start <= number < end:
            return {"id": card, "species": species, "small": small, "large": large,
                    "image": f"public/assets/cubirds/cards/deck-{deck}-{number:02}.webp"}
    raise GameError("无效鸟牌。")


def splendor_cards() -> dict[str, dict]:
    cards = {}
    for obj in MANIFESTS["splendor"]["objects"]:
        if obj["type"] != "Card" or not obj["image"] or not obj["name"]:
            continue
        bits = obj["name"].split()
        if len(bits) < 4 or not bits[0].isdigit() or bits[2] not in COLORS:
            continue
        tier = {5: 1, 6: 2, 7: 3}.get(obj["card_id"] // 100)
        if tier is None:
            continue
        cost = {color: int(n) for n, color in re.findall(r"(\d+)([wugrb])", bits[3])}
        card_id = f"s{bits[0]}"
        cards[card_id] = {"id": card_id, "tier": tier, "points": int(bits[1]),
                          "bonus": bits[2], "cost": cost, "image": f"public/assets/splendor/{obj['image']}"}
    return cards


SPLENDOR_CARDS = splendor_cards()
NOBLES = [
    {"id": f"n{i}", "cost": {color: int(n) for n, color in re.findall(r"(\d+)([wugrb])", obj["name"])},
     "image": f"public/assets/splendor/{obj['custom_image']}"}
    for i, obj in enumerate(MANIFESTS["splendor"]["objects"])
    if obj["type"] == "Custom_Tile" and obj["custom_image"] and re.search(r"\d+[wugrb]", obj["name"])
]
AVALON_ART = {
    obj["description"]: f"public/assets/avalon/{obj['image']}"
    for obj in MANIFESTS["avalon"]["objects"]
    if obj["type"] == "Card" and obj["image"] and obj["description"]
}


@dataclass
class PartyRoom:
    code: str
    group_id: str
    players: list[Player]
    game: str
    mode: str = "basic"
    phase: str = "lobby"
    state: dict = field(default_factory=dict)
    log: list[str] = field(default_factory=list)
    revision: int = 0

    def player(self, qq_id: str) -> Player:
        for player in self.players:
            if player.qq_id == qq_id:
                return player
        raise GameError("你不在本房间的 QQ 组局名单里。")

    def _record(self, message: str) -> None:
        self.log.append(message)
        self.log = self.log[-30:]
        self.revision += 1

    def add_player(self, qq_id: str, name: str) -> None:
        if self.phase != "lobby":
            raise GameError("游戏已经开始，无法加入。")
        if any(player.qq_id == qq_id for player in self.players):
            raise GameError("你已经在房间里。")
        if len(self.players) >= LIMITS[self.game][1]:
            raise GameError(f"{NAMES[self.game]}最多支持 {LIMITS[self.game][1]} 人。")
        self.players.append(Player(qq_id, name[:24]))
        self._record(f"{name[:24]} 加入了房间。")

    def start(self, rng: random.Random | None = None) -> None:
        if self.phase != "lobby":
            raise GameError("游戏已经开始。")
        low, high = LIMITS[self.game]
        if not low <= len(self.players) <= high:
            raise GameError(f"需要 {low}–{high} 位玩家才能开始。")
        rng = rng or random.SystemRandom()
        getattr(self, f"_start_{self.game}")(rng)
        self.phase = "playing"
        self._record(f"{NAMES[self.game]}开始，轮到 {self.players[self.state.get('current', 0)].name}。")

    def _next(self) -> None:
        current = self.state["current"]
        for step in range(1, len(self.players) + 1):
            candidate = (current + step) % len(self.players)
            if self.players[candidate].alive:
                self.state["current"] = candidate
                self._record(f"轮到 {self.players[candidate].name}。")
                return

    def _turn(self, player: Player) -> None:
        if self.phase != "playing" or self.players[self.state["current"]] is not player:
            raise GameError("现在不是你的回合。")

    def action(self, qq_id: str, action: dict) -> None:
        player = self.player(qq_id)
        if self.phase != "playing":
            raise GameError("游戏尚未开始或已经结束。")
        getattr(self, f"_act_{self.game}")(player, action)

    # CuBirds ---------------------------------------------------------------
    def _bird_draw(self, count: int) -> list[str]:
        state = self.state
        if len(state["deck"]) < count and state["discard"]:
            state["deck"] += state["discard"]
            state["discard"] = []
            random.shuffle(state["deck"])
        drawn = []
        for _ in range(min(count, len(state["deck"]))):
            drawn.append(state["deck"].pop())
        return drawn

    def _start_cubirds(self, rng: random.Random) -> None:
        deck = [f"b{deck}-{i:02}" for deck, ranges in BIRD_RANGES.items()
                for start, end, *_ in ranges for i in range(start, end)]
        rng.shuffle(deck)
        self.state = {"deck": deck, "discard": [], "rows": [[], [], [], []],
                      "collection": {p.qq_id: [] for p in self.players},
                      "current": 0, "stage": "place", "can_draw_two": False, "flock_done": False}
        for row in self.state["rows"]:
            while len(row) < 3:
                card = self._bird_draw(1)[0]
                if bird(card)["species"] in {bird(item)["species"] for item in row}:
                    self.state["discard"].append(card)
                else:
                    row.append(card)
        self.state["deck"] += self.state["discard"]
        self.state["discard"] = []
        rng.shuffle(self.state["deck"])
        for player in self.players:
            player.hand = self._bird_draw(8)
            self.state["collection"][player.qq_id] = self._bird_draw(1)

    def _act_cubirds(self, player: Player, action: dict) -> None:
        self._turn(player)
        state = self.state
        kind = action.get("type")
        if kind == "place":
            if state["stage"] != "place":
                raise GameError("请先结束当前回合。")
            species, row_index, side = action.get("species"), action.get("row"), action.get("side")
            if not isinstance(row_index, int) or row_index not in range(4) or side not in ("left", "right"):
                raise GameError("请选择一行及摆放方向。")
            played = [card for card in player.hand if bird(card)["species"] == species]
            if not played:
                raise GameError("手中没有这种鸟。")
            player.hand = [card for card in player.hand if card not in played]
            row = state["rows"][row_index]
            if side == "left":
                match = next((i for i, card in enumerate(row) if bird(card)["species"] == species), None)
                taken = row[:match] if match is not None else []
                row[:match if match is not None else 0] = played
                if match is not None:
                    del row[len(played):len(played) + len(taken)]
            else:
                match = next((i for i in range(len(row) - 1, -1, -1) if bird(row[i])["species"] == species), None)
                taken = row[match + 1:] if match is not None else []
                if match is not None:
                    del row[match + 1:]
                row.extend(played)
            player.hand += taken
            if taken:
                while len({bird(card)["species"] for card in row}) == 1 and (state["deck"] or state["discard"]):
                    row += self._bird_draw(1)
            state["can_draw_two"] = not taken
            state["stage"] = "flock"
            state["flock_done"] = False
            self._record(f"{player.name} 在第 {row_index + 1} 行摆出 {len(played)} 张{species}，收回 {len(taken)} 张牌。")
        elif kind == "draw_two":
            if state["stage"] != "flock" or not state["can_draw_two"]:
                raise GameError("现在不能额外抽牌。")
            player.hand += self._bird_draw(2)
            state["can_draw_two"] = False
            self._record(f"{player.name} 从牌堆补了两张牌。")
        elif kind == "flock":
            if state["stage"] != "flock":
                raise GameError("请先摆出鸟牌。")
            if state["flock_done"]:
                raise GameError("每回合只能完成一个鸟群。")
            species = action.get("species")
            matching = [card for card in player.hand if bird(card)["species"] == species]
            if not matching:
                raise GameError("手中没有这种鸟。")
            info = bird(matching[0])
            big = len(matching) >= info["large"]
            if len(matching) < info["small"]:
                raise GameError("鸟群数量不足。")
            keep = 2 if big else 1
            player.hand = [card for card in player.hand if card not in matching]
            state["collection"][player.qq_id] += matching[:keep]
            state["discard"] += matching[keep:]
            state["flock_done"] = True
            counts = Counter(bird(card)["species"] for card in state["collection"][player.qq_id])
            self._record(f"{player.name} 完成{species}鸟群，收集 {keep} 张。")
            if len(counts) >= 7 or sum(n >= 3 for n in counts.values()) >= 2:
                self.phase = "finished"
                state["winner"] = player.qq_id
                self._record(f"{player.name} 获胜！")
        elif kind == "end_turn":
            if state["stage"] != "flock":
                raise GameError("请先摆出鸟牌。")
            if not player.hand:
                for other in self.players:
                    state["discard"] += other.hand
                    other.hand = []
                if len(state["deck"]) + len(state["discard"]) < 8 * len(self.players):
                    counts = {p.qq_id: len(state["collection"][p.qq_id]) for p in self.players}
                    state["winner"] = max(counts, key=counts.get)
                    self.phase = "finished"
                    self._record(f"牌堆不足以发新手牌，{self.player(state['winner']).name} 收集最多鸟牌获胜。")
                    return
                for other in self.players:
                    other.hand = self._bird_draw(8)
                self._record("一轮结束，所有玩家重新摸 8 张牌。")
                state["stage"] = "place"
                state["can_draw_two"] = False
                state["flock_done"] = False
                self._record(f"{player.name} 率先清空手牌，继续先手。")
                return
            state["stage"] = "place"
            state["can_draw_two"] = False
            state["flock_done"] = False
            self._next()
        else:
            raise GameError("未知方·鸟操作。")

    # Splendor --------------------------------------------------------------
    def _start_splendor(self, rng: random.Random) -> None:
        deck = {str(tier): [card_id for card_id, card in SPLENDOR_CARDS.items() if card["tier"] == tier]
                for tier in (1, 2, 3)}
        for cards in deck.values():
            rng.shuffle(cards)
        nobles = [noble["id"] for noble in NOBLES]
        rng.shuffle(nobles)
        gems = {color: {2: 4, 3: 5, 4: 7}[len(self.players)] for color in COLORS}
        gems["j"] = 5
        self.state = {"deck": deck, "market": {tier: [deck[tier].pop() for _ in range(4)] for tier in deck},
                      "nobles": nobles[:len(self.players) + 1], "bank": gems,
                      "hold": {p.qq_id: {color: 0 for color in GEM_NAMES} for p in self.players},
                      "built": {p.qq_id: [] for p in self.players},
                      "reserved": {p.qq_id: [] for p in self.players},
                      "claimed": {p.qq_id: [] for p in self.players},
                      "current": 0, "turns": 0, "final_round": False}

    def _splendor_bonus(self, qq_id: str) -> Counter:
        return Counter(SPLENDOR_CARDS[card]["bonus"] for card in self.state["built"][qq_id])

    def _splendor_finish(self, player: Player) -> None:
        state = self.state
        bonus = self._splendor_bonus(player.qq_id)
        eligible = [n for n in NOBLES if n["id"] in state["nobles"] and
                    all(bonus[color] >= count for color, count in n["cost"].items())]
        if eligible:
            noble = eligible[0]
            state["nobles"].remove(noble["id"])
            state["claimed"][player.qq_id].append(noble["id"])
            self._record(f"{player.name} 获得一位贵族的访问。")
        score = sum(SPLENDOR_CARDS[c]["points"] for c in state["built"][player.qq_id]) + 3 * len(state["claimed"][player.qq_id])
        if score >= 15:
            state["final_round"] = True
        state["turns"] += 1
        if state["final_round"] and state["turns"] % len(self.players) == 0:
            scores = {p.qq_id: sum(SPLENDOR_CARDS[c]["points"] for c in state["built"][p.qq_id]) + 3 * len(state["claimed"][p.qq_id]) for p in self.players}
            state["winner"] = max(scores, key=lambda qq: (scores[qq], -len(state["built"][qq])))
            self.phase = "finished"
            self._record(f"游戏结束，{self.player(state['winner']).name} 获胜。")
        else:
            self._next()

    def _act_splendor(self, player: Player, action: dict) -> None:
        self._turn(player)
        state = self.state
        qq = player.qq_id
        kind = action.get("type")
        if kind == "take":
            colors = action.get("colors") or []
            if not isinstance(colors, list) or not colors or any(color not in COLORS for color in colors):
                raise GameError("请选择要领取的宝石。")
            if len(colors) == 2 and colors[0] == colors[1]:
                if state["bank"][colors[0]] < 4:
                    raise GameError("同色拿两枚时，供应区需至少有 4 枚。")
            elif len(colors) > 3 or len(set(colors)) != len(colors):
                raise GameError("每回合可拿至多 3 种不同颜色，或同色 2 枚。")
            elif len(colors) < min(3, sum(state["bank"][color] > 0 for color in COLORS)):
                raise GameError("有足够颜色时必须选择 3 种不同宝石。")
            if any(state["bank"][color] < colors.count(color) for color in set(colors)):
                raise GameError("供应区宝石不足。")
            returns = action.get("returns") or []
            if any(color not in GEM_NAMES for color in returns):
                raise GameError("归还的宝石颜色无效。")
            available = Counter(state["hold"][qq]) + Counter(colors)
            if any(Counter(returns)[color] > available[color] for color in GEM_NAMES):
                raise GameError("不能归还自己没有的宝石。")
            after = available - Counter(returns)
            if sum(after.values()) > 10:
                raise GameError("回合结束最多持有 10 枚宝石，请选择归还。")
            for color in colors:
                state["bank"][color] -= 1
            for color in returns:
                state["bank"][color] += 1
            state["hold"][qq] = {color: after[color] for color in GEM_NAMES}
            self._record(f"{player.name} 领取了宝石。")
        elif kind in ("reserve", "buy"):
            card_id = action.get("card")
            tier = str(action.get("tier"))
            market = state["market"].get(tier, [])
            from_market = card_id in market
            from_reserve = card_id in state["reserved"][qq]
            if kind == "reserve":
                if len(state["reserved"][qq]) >= 3:
                    raise GameError("最多保留 3 张牌。")
                if card_id == "deck":
                    if not state["deck"].get(tier):
                        raise GameError("该等级牌堆已经抽完。")
                    card_id = state["deck"][tier].pop()
                elif not from_market:
                    raise GameError("只能保留场上卡牌或盲抽牌堆。")
                if from_market:
                    market.remove(card_id)
                    if state["deck"][tier]:
                        market.append(state["deck"][tier].pop())
                state["reserved"][qq].append(card_id)
                if state["bank"]["j"] and sum(state["hold"][qq].values()) < 10:
                    state["bank"]["j"] -= 1
                    state["hold"][qq]["j"] += 1
                self._record(f"{player.name} 保留了一张卡牌。")
            else:
                if not (from_market or from_reserve) or card_id not in SPLENDOR_CARDS:
                    raise GameError("请选择可购买的卡牌。")
                card = SPLENDOR_CARDS[card_id]
                bonus = self._splendor_bonus(qq)
                need = {color: max(0, card["cost"].get(color, 0) - bonus[color]) for color in COLORS}
                shortage = sum(max(0, need[color] - state["hold"][qq][color]) for color in COLORS)
                if shortage > state["hold"][qq]["j"]:
                    raise GameError("宝石不足，无法购买。")
                gold = 0
                for color in COLORS:
                    paid = min(need[color], state["hold"][qq][color])
                    state["hold"][qq][color] -= paid
                    state["bank"][color] += paid
                    gold += need[color] - paid
                state["hold"][qq]["j"] -= gold
                state["bank"]["j"] += gold
                (market if from_market else state["reserved"][qq]).remove(card_id)
                if from_market and state["deck"][tier]:
                    market.append(state["deck"][tier].pop())
                state["built"][qq].append(card_id)
                self._record(f"{player.name} 购买了一张 {card['tier']} 级发展卡。")
        else:
            raise GameError("未知璀璨宝石操作。")
        self._splendor_finish(player)

    # Avalon ----------------------------------------------------------------
    def _start_avalon(self, rng: random.Random) -> None:
        count = len(self.players)
        good = ["梅林", "派西维尔"] if self.mode != "basic" else ["梅林"]
        evil = ["刺客"]
        if self.mode != "basic":
            evil += ["莫甘娜"]
            if count == 7 or count == 10:
                evil += ["奥伯伦"]
            if count >= 9:
                evil += ["莫德雷德"]
        good += ["忠臣"] * (GOOD_COUNTS[count] - len(good))
        evil += ["爪牙"] * (count - GOOD_COUNTS[count] - len(evil))
        roles = good + evil
        rng.shuffle(roles)
        self.state = {"roles": dict(zip((p.qq_id for p in self.players), roles)),
                      "current": 0, "quest": 0, "results": [], "rejections": 0,
                      "stage": "propose", "team": [], "votes": {}, "quest_votes": {}, "winner": None}

    def _act_avalon(self, player: Player, action: dict) -> None:
        state = self.state
        kind = action.get("type")
        if kind == "propose":
            self._turn(player)
            if state["stage"] != "propose":
                raise GameError("当前不能提名队伍。")
            team = action.get("team") or []
            if len(team) != QUEST_SIZES[len(self.players)][state["quest"]] or len(set(team)) != len(team) or any(id_ not in state["roles"] for id_ in team):
                raise GameError("任务队伍人数或成员不正确。")
            state["team"] = team
            state["votes"] = {}
            state["stage"] = "team_vote"
            self._record(f"{player.name} 提名了任务队伍，等待全员投票。")
        elif kind == "team_vote":
            if state["stage"] != "team_vote" or player.qq_id in state["votes"]:
                raise GameError("当前不能重复投票。")
            if action.get("vote") not in ("approve", "reject"):
                raise GameError("请选择赞成或反对。")
            state["votes"][player.qq_id] = action["vote"]
            if len(state["votes"]) == len(self.players):
                approves = sum(v == "approve" for v in state["votes"].values())
                if approves <= len(self.players) // 2:
                    state["rejections"] += 1
                    self._record(f"提案未通过（{approves} 票赞成）。")
                    if state["rejections"] >= 5:
                        state["winner"] = "evil"
                        self.phase = "finished"
                        self._record("连续五次提案失败，邪恶阵营获胜。")
                    else:
                        state["stage"] = "propose"
                        self._next()
                else:
                    state["stage"] = "quest_vote"
                    state["quest_votes"] = {}
                    self._record(f"提案通过（{approves} 票赞成），队员秘密提交任务牌。")
        elif kind == "quest_vote":
            if state["stage"] != "quest_vote" or player.qq_id not in state["team"] or player.qq_id in state["quest_votes"]:
                raise GameError("你不能在当前任务投票。")
            vote = action.get("vote")
            if vote not in ("success", "fail") or (state["roles"][player.qq_id] not in EVIL_ROLES and vote == "fail"):
                raise GameError("只能提交合法的任务牌。")
            state["quest_votes"][player.qq_id] = vote
            if len(state["quest_votes"]) == len(state["team"]):
                failures = sum(v == "fail" for v in state["quest_votes"].values())
                threshold = 2 if len(self.players) >= 7 and state["quest"] == 3 else 1
                success = failures < threshold
                state["results"].append(success)
                self._record(f"第 {state['quest'] + 1} 次任务{'成功' if success else '失败'}，收到 {failures} 张失败牌。")
                if sum(state["results"]) >= 3:
                    state["stage"] = "assassinate"
                    self._record("正义方完成三次任务，刺客现在可选择刺杀对象。")
                elif len(state["results"]) - sum(state["results"]) >= 3:
                    state["winner"] = "evil"
                    self.phase = "finished"
                    self._record("邪恶阵营获胜。")
                else:
                    state["quest"] += 1
                    state["stage"] = "propose"
                    state["rejections"] = 0
                    self._next()
        elif kind == "assassinate":
            if state["stage"] != "assassinate" or state["roles"][player.qq_id] != "刺客":
                raise GameError("只有刺客可以指定刺杀对象。")
            target = action.get("target")
            if target not in state["roles"] or target == player.qq_id:
                raise GameError("请选择有效玩家。")
            state["winner"] = "evil" if state["roles"][target] == "梅林" else "good"
            self.phase = "finished"
            self._record(f"刺客指向 {self.player(target).name}；{'邪恶' if state['winner'] == 'evil' else '正义'}阵营获胜。")
        else:
            raise GameError("未知阿瓦隆操作。")

    # Coup: social bluff adjudication is deliberately player-confirmed. -----
    def _start_coup(self, rng: random.Random) -> None:
        roles = ["公爵", "上尉", "刺客", "女爵", "判官" if self.mode != "basic" else "大使"]
        copies = 5 if len(self.players) > 6 else 3
        deck = [role for role in roles for _ in range(copies)]
        rng.shuffle(deck)
        self.state = {"deck": deck, "coins": {p.qq_id: 2 for p in self.players},
                      "lost": {p.qq_id: [] for p in self.players},
                      "factions": {p.qq_id: "改革" if i % 2 else "秩序" for i, p in enumerate(self.players)} if self.mode != "basic" else {},
                      "treasury": 0, "current": 0, "pending": None, "winner": None}
        for player in self.players:
            player.hand = [deck.pop(), deck.pop()]

    def _coup_end(self) -> None:
        alive = [p for p in self.players if p.alive]
        if len(alive) == 1:
            self.state["winner"] = alive[0].qq_id
            self.phase = "finished"
            self._record(f"{alive[0].name} 赢得政变。")
        else:
            self._next()

    def _act_coup(self, player: Player, action: dict) -> None:
        state = self.state
        kind = action.get("type")
        pending = state["pending"]
        if kind == "declare":
            self._turn(player)
            if pending:
                raise GameError("请先完成上一个行动的争议判定。")
            move = action.get("move")
            target = action.get("target")
            options = {"income", "aid", "tax", "steal", "assassinate", "coup", "exchange", "inspect", "convert", "embezzle"}
            if move not in options or (self.mode == "basic" and move in {"inspect", "convert", "embezzle"}):
                raise GameError("当前模式不支持这个行动。")
            if state["coins"][player.qq_id] >= 10 and move != "coup":
                raise GameError("拥有至少 10 枚硬币时必须发动政变。")
            if move in {"steal", "assassinate", "coup", "inspect", "convert"}:
                if target not in state["coins"] or not self.player(target).alive or (target == player.qq_id and move != "convert"):
                    raise GameError("请选择另一位在场玩家。")
                if move in {"steal", "assassinate", "coup", "inspect"} and state["factions"]:
                    if state["factions"][target] == state["factions"][player.qq_id] and len({state["factions"][p.qq_id] for p in self.players if p.alive}) > 1:
                        raise GameError("扩展规则中，不能对同阵营玩家发动此行动。")
            if move in {"assassinate", "coup"}:
                cost = 3 if move == "assassinate" else 7
                if state["coins"][player.qq_id] < cost:
                    raise GameError("硬币不足。")
                state["coins"][player.qq_id] -= cost
            state["pending"] = {"actor": player.qq_id, "move": move, "target": target,
                                "blocked": False, "blocker": None, "block_role": None}
            self._record(f"{player.name} 宣布了行动：{move}。请在群内讨论质疑与阻挡，然后在网页确认结果。")
        elif kind == "block":
            if not pending or player.qq_id == pending["actor"] or pending["blocked"]:
                raise GameError("当前不能阻挡。")
            if pending["move"] not in {"aid", "steal", "assassinate"}:
                raise GameError("此行动不能阻挡。")
            if pending["move"] != "aid" and player.qq_id != pending["target"]:
                raise GameError("只有行动目标可以阻挡。")
            role = action.get("role")
            allowed = {"aid": {"公爵"}, "steal": {"上尉", "大使", "判官"}, "assassinate": {"女爵"}}[pending["move"]]
            if role not in allowed:
                raise GameError("所选角色不能阻挡此行动。")
            pending.update(blocked=True, blocker=player.qq_id, block_role=role)
            self._record(f"{player.name} 声明以{role}阻挡；其他玩家可在群内质疑。")
        elif kind == "overrule_block":
            self._turn(player)
            if not pending or not pending["blocked"]:
                raise GameError("当前没有待质疑的阻挡。")
            pending["blocked"] = False
            self._record("阻挡被质疑并判定无效，原行动继续。")
        elif kind == "reveal":
            if not pending or action.get("card") not in player.hand:
                raise GameError("请选择自己持有的影响牌。")
            card = action["card"]
            player.hand.remove(card)
            state["lost"][player.qq_id].append(card)
            player.alive = bool(player.hand)
            self._record(f"{player.name} 失去一张{card}影响牌。")
            if not player.alive:
                self._record(f"{player.name} 出局。")
        elif kind == "prove":
            if not pending or action.get("card") not in player.hand:
                raise GameError("请选择要证明的影响牌。")
            if player.qq_id != (pending["blocker"] if pending["blocked"] else pending["actor"]):
                raise GameError("只有当前声明角色的玩家可以亮牌证明。")
            role = pending["block_role"] if pending["blocked"] and pending["blocker"] == player.qq_id else {
                "tax": "公爵", "steal": "上尉", "assassinate": "刺客", "exchange": "判官" if self.mode != "basic" else "大使", "inspect": "判官"
            }.get(pending["move"])
            if action["card"] != role:
                raise GameError("这张牌不能证明所声明的角色。")
            player.hand.remove(role)
            state["deck"].append(role)
            random.shuffle(state["deck"])
            player.hand.append(state["deck"].pop())
            self._record(f"{player.name} 证明了{role}，将牌洗回并补一张。质疑者须自行失去一张影响牌。")
        elif kind == "resolve":
            self._turn(player)
            if not pending:
                raise GameError("没有待结算行动。")
            if any(pending.get(key) for key in ("must_lose", "exchange", "inspection")):
                raise GameError("请先完成当前影响牌操作。")
            move = pending["move"]
            target = pending["target"]
            if not pending["blocked"] and action.get("apply", True):
                if move == "income": state["coins"][player.qq_id] += 1
                elif move == "aid": state["coins"][player.qq_id] += 2
                elif move == "tax": state["coins"][player.qq_id] += 3
                elif move == "steal":
                    amount = min(2, state["coins"][target])
                    state["coins"][target] -= amount
                    state["coins"][player.qq_id] += amount
                elif move == "coup" or move == "assassinate":
                    if self.player(target).alive:
                        state["pending"]["must_lose"] = target
                        self._record(f"{self.player(target).name} 须选择一张影响牌失去。")
                        return
                elif move == "exchange":
                    drawn = [state["deck"].pop() for _ in range(min(2, len(state["deck"]))) ]
                    player.hand += drawn
                    state["pending"]["exchange"] = True
                    self._record(f"{player.name} 抽取额外影响牌，须选牌归还。")
                    return
                elif move == "inspect":
                    target_player = self.player(target)
                    if not target_player.hand:
                        raise GameError("目标已没有影响牌。")
                    pending["inspection"] = random.choice(target_player.hand)
                    self._record(f"{player.name} 查看了 {target_player.name} 的一张影响牌。")
                    return
                elif move == "convert":
                    cost = 1 if target == player.qq_id else 2
                    if state["coins"][player.qq_id] < cost:
                        raise GameError("硬币不足。")
                    state["coins"][player.qq_id] -= cost
                    state["treasury"] += cost
                    state["factions"][target] = "改革" if state["factions"][target] == "秩序" else "秩序"
                elif move == "embezzle":
                    state["coins"][player.qq_id] += state["treasury"]
                    state["treasury"] = 0
            state["pending"] = None
            self._record(f"{player.name} 的行动已结算{'（被阻挡或取消）' if pending['blocked'] or not action.get('apply', True) else ''}。")
            self._coup_end()
        elif kind == "exchange_finish":
            self._turn(player)
            if not pending or not pending.get("exchange"):
                raise GameError("当前没有交换牌。")
            returns = action.get("cards") or []
            if len(returns) != len(player.hand) - 2 or any(returns.count(card) > player.hand.count(card) for card in set(returns)):
                raise GameError("请选择正确数量的牌归还牌库。")
            for card in returns:
                player.hand.remove(card)
            state["deck"] += returns
            random.shuffle(state["deck"])
            state["pending"] = None
            self._record(f"{player.name} 完成影响牌交换。")
            self._coup_end()
        elif kind == "inspect_finish":
            self._turn(player)
            if not pending or pending["actor"] != player.qq_id or not pending.get("inspection"):
                raise GameError("当前没有待完成的检视。")
            if action.get("replace"):
                target_player = self.player(pending["target"])
                target_player.hand.remove(pending["inspection"])
                state["deck"].append(pending["inspection"])
                random.shuffle(state["deck"])
                target_player.hand.append(state["deck"].pop())
                self._record(f"{target_player.name} 按判官要求更换了一张影响牌。")
            state["pending"] = None
            self._coup_end()
        elif kind == "lose_finish":
            if not pending or pending.get("must_lose") != player.qq_id or action.get("card") not in player.hand:
                raise GameError("请选择要失去的一张影响牌。")
            card = action["card"]
            player.hand.remove(card)
            state["lost"][player.qq_id].append(card)
            player.alive = bool(player.hand)
            state["pending"] = None
            self._record(f"{player.name} 失去一张{card}影响牌。")
            self._coup_end()
        else:
            raise GameError("未知政变操作。")

    def view(self, qq_id: str | None = None) -> dict:
        me = self.player(qq_id) if qq_id else None
        state = self.state
        public = {key: value for key, value in state.items() if key not in {"deck", "roles", "quest_votes"}}
        if self.game == "splendor" and state:
            public["decks"] = {tier: len(cards) for tier, cards in state["deck"].items()}
            public["reserved"] = {id_: (cards if me and id_ == me.qq_id else len(cards))
                                  for id_, cards in state["reserved"].items()}
        if self.game == "cubirds" and state:
            public["deckCount"] = len(state["deck"])
            public["discardCount"] = len(state["discard"])
            public.pop("discard", None)
        if self.game == "coup" and state:
            public["deckCount"] = len(state["deck"])
            if public.get("pending") and public["pending"].get("inspection"):
                public["pending"] = dict(public["pending"])
                if not me or public["pending"]["actor"] != me.qq_id:
                    public["pending"].pop("inspection", None)
        if self.game == "avalon" and state:
            public["voteCount"] = len(state["votes"])
            public["questVoteCount"] = len(state["quest_votes"])
            if state["stage"] == "team_vote" and len(state["votes"]) < len(self.players):
                public["votes"] = {id_: True for id_ in state["votes"]}
            public["quest_votes"] = {id_: True for id_ in state["quest_votes"]}
        view = {
            "code": self.code, "game": self.game, "name": NAMES[self.game], "mode": self.mode,
            "phase": self.phase, "revision": self.revision, "state": public,
            "players": [{"id": p.qq_id, "name": p.name, "alive": p.alive, "cards": len(p.hand),
                         "avatar": p.avatar, "claimed": bool(p.token)} for p in self.players],
            "current": self.players[state["current"]].qq_id if state and self.phase != "lobby" else None,
            "log": self.log[-16:],
            "me": {"id": me.qq_id, "name": me.name, "hand": me.hand} if me else None,
        }
        if me and self.game == "avalon" and state:
            role = state["roles"][me.qq_id]
            known = []
            if role == "梅林":
                known = [p.qq_id for p in self.players if p.qq_id != me.qq_id and
                         state["roles"][p.qq_id] in EVIL_ROLES - {"莫德雷德"}]
            elif role == "派西维尔":
                known = [p.qq_id for p in self.players if state["roles"][p.qq_id] in {"梅林", "莫甘娜"}]
            elif role in EVIL_ROLES - {"奥伯伦"}:
                known = [p.qq_id for p in self.players if p.qq_id != me.qq_id and
                         state["roles"][p.qq_id] in EVIL_ROLES - {"奥伯伦"}]
            view["me"].update(role=role, known=known, roleImage=AVALON_ART.get({
                "梅林": "Merlin", "派西维尔": "Percival", "刺客": "Assassin",
                "莫甘娜": "Morgana", "莫德雷德": "Mordred", "奥伯伦": "Oberon",
                "忠臣": "Loyal Servant of Arthur", "爪牙": "Minion of Mordred"}[role]))
        return view
