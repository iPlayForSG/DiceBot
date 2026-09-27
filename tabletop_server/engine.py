"""Server-side Exploding Kittens game state.

The card manifest is imported from the specified TTS workshop item. The game
logic intentionally lives on the server so private hands never reach other
players' browsers.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from pathlib import Path
import json


MANIFEST = json.loads(
    (Path(__file__).resolve().parents[1] / "web/public/assets/exploding-kittens/manifest.json").read_text(
        encoding="utf-8"
    )
)
CARDS = {card["id"]: card for card in MANIFEST["cards"]}
LABELS = {
    "bomb": "炸弹猫咪", "defuse": "拆弹", "attack": "攻击", "skip": "跳过",
    "shuffle": "洗牌", "see": "预知", "favor": "帮帮忙", "nope": "不行", "cat": "猫牌",
}


class GameError(ValueError):
    pass


@dataclass
class Player:
    qq_id: str
    name: str
    alive: bool = True
    hand: list[str] = field(default_factory=list)
    token: str | None = None
    avatar: bool = False
    claim_code: str | None = None


@dataclass
class GameRoom:
    code: str
    group_id: str
    players: list[Player]
    mode: str = "basic"
    phase: str = "lobby"
    deck: list[str] = field(default_factory=list)
    discard: list[str] = field(default_factory=list)
    current: int = 0
    draws_due: int = 1
    pending: dict | None = None
    awaiting: dict | None = None
    peek: dict[str, list[str]] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)
    revision: int = 0
    created_at: float = field(default_factory=time.time)

    def player(self, qq_id: str) -> Player:
        for player in self.players:
            if player.qq_id == qq_id:
                return player
        raise GameError("你不在本房间的 QQ 组局名单里。")

    @property
    def active(self) -> Player:
        return self.players[self.current]

    def _record(self, message: str) -> None:
        self.log.append(message)
        self.log = self.log[-30:]
        self.revision += 1

    def _next(self, due: int = 1) -> None:
        if sum(player.alive for player in self.players) <= 1:
            self.phase = "finished"
            winner = next((p for p in self.players if p.alive), None)
            self._record(f"游戏结束，{winner.name if winner else '无人'}获胜！")
            return
        for offset in range(1, len(self.players) + 1):
            index = (self.current + offset) % len(self.players)
            if self.players[index].alive:
                self.current = index
                self.draws_due = due
                self._record(f"轮到 {self.active.name}，需要完成 {due} 次回合。")
                return

    def add_player(self, qq_id: str, name: str) -> None:
        if self.phase != "lobby":
            raise GameError("游戏已经开始，无法加入。")
        if any(p.qq_id == qq_id for p in self.players):
            raise GameError("你已经在房间里。")
        if len(self.players) >= 5:
            raise GameError("炸弹猫最多支持 5 人。")
        self.players.append(Player(qq_id, name[:24]))
        self._record(f"{name[:24]} 加入了房间。")

    def start(self, rng: random.Random | None = None) -> None:
        if self.phase != "lobby":
            raise GameError("游戏已经开始。")
        if not 2 <= len(self.players) <= 5:
            raise GameError("需要 2–5 位玩家才能开始。")
        rng = rng or random.SystemRandom()
        normal = [card_id for card_id, card in CARDS.items() if card["kind"] not in {"bomb", "defuse"}]
        defuses = [card_id for card_id, card in CARDS.items() if card["kind"] == "defuse"]
        bombs = [card_id for card_id, card in CARDS.items() if card["kind"] == "bomb"]
        rng.shuffle(normal)
        rng.shuffle(defuses)
        rng.shuffle(bombs)
        for player in self.players:
            player.hand = [defuses.pop()] + [normal.pop() for _ in range(7)]
        self.deck = normal + defuses + bombs[:len(self.players) - 1]
        rng.shuffle(self.deck)
        self.phase = "playing"
        self.current = 0
        self.draws_due = 1
        self._record(f"游戏开始，轮到 {self.active.name}。")

    def _take_hand(self, player: Player, card_id: str, expected: str | None = None) -> str:
        if card_id not in player.hand:
            raise GameError("你没有这张牌。")
        kind = CARDS[card_id]["kind"]
        if expected and kind != expected:
            raise GameError(f"这张牌不是{LABELS[expected]}。")
        player.hand.remove(card_id)
        return kind

    @staticmethod
    def _signature(card_id: str) -> str:
        card = CARDS[card_id]
        return f"cat:{card['face']}" if card["kind"] == "cat" else card["kind"]

    def play(self, qq_id: str, card_id: str, target: str | None = None, second: str | None = None) -> None:
        player = self.player(qq_id)
        if self.phase != "playing":
            raise GameError("游戏尚未开始或已经结束。")
        if self.pending or self.awaiting:
            raise GameError("请先完成当前卡牌效果。")
        if player != self.active or not player.alive:
            raise GameError("现在不是你的回合。")
        if card_id not in player.hand:
            raise GameError("你没有这张牌。")
        kind = CARDS[card_id]["kind"]
        if kind in {"bomb", "defuse", "nope"}:
            raise GameError("这张牌不能这样打出。")
        if kind in {"favor", "cat"}:
            other = self.player(target or "")
            if other == player or not other.alive:
                raise GameError("请选择另一位仍在游戏中的玩家。")
        if kind == "cat":
            if not second or second == card_id or second not in player.hand:
                raise GameError("猫牌需要选择两张相同的牌。")
            if CARDS[second]["kind"] != "cat" or CARDS[second]["face"] != CARDS[card_id]["face"]:
                raise GameError("两张猫牌必须相同。")
            player.hand.remove(second)
            self.discard.append(second)
        player.hand.remove(card_id)
        self.discard.append(card_id)
        self.pending = {"actor": qq_id, "kind": kind, "target": target, "nopes": 0}
        self._record(f"{player.name} 打出{LABELS[kind]}。其他玩家可以打出「不行」反制。")

    def play_combo(
        self, qq_id: str, card_ids: list[str], target: str | None = None,
        declared: str | None = None, retrieve: str | None = None,
    ) -> None:
        player = self.player(qq_id)
        if self.phase != "playing" or player != self.active or self.pending or self.awaiting:
            raise GameError("现在不能打出组合。")
        if len(card_ids) not in (2, 3, 5) or len(set(card_ids)) != len(card_ids):
            raise GameError("组合必须是 2、3 或 5 张不同的实体牌。")
        if any(card_id not in player.hand for card_id in card_ids):
            raise GameError("所选卡牌不都在你的手牌里。")
        signatures = [self._signature(card_id) for card_id in card_ids]
        count = len(card_ids)
        if self.mode == "basic" and (count != 2 or not signatures[0].startswith("cat:")):
            raise GameError("基础版只能用两张相同猫牌组成组合。")
        if count in (2, 3):
            if len(set(signatures)) != 1:
                raise GameError("两张或三张组合必须是相同的牌。")
            other = self.player(target or "")
            if other == player or not other.alive:
                raise GameError("请选择另一位仍在游戏中的玩家。")
        elif len(set(signatures)) != 5:
            raise GameError("五张组合必须各不相同。")
        if count == 3:
            if self.mode != "advanced" or declared not in {self._signature(id_) for id_ in CARDS}:
                raise GameError("请选择要索取的有效牌名。")
        if count == 5:
            if self.mode != "advanced" or not retrieve or retrieve not in self.discard:
                raise GameError("请选择一张已有的弃牌。")
        for card_id in card_ids:
            player.hand.remove(card_id)
            self.discard.append(card_id)
        kind = {2: "pair", 3: "triple", 5: "five"}[count]
        self.pending = {
            "actor": qq_id, "kind": kind, "target": target,
            "declared": declared, "retrieve": retrieve, "nopes": 0,
        }
        self._record(f"{player.name} 打出{count}张牌组合。其他玩家可以打出「不行」反制。")

    def nope(self, qq_id: str, card_id: str) -> None:
        player = self.player(qq_id)
        if not self.pending or not player.alive:
            raise GameError("当前没有可反制的牌。")
        self._take_hand(player, card_id, "nope")
        self.discard.append(card_id)
        self.pending["nopes"] += 1
        self._record(f"{player.name} 打出「不行」；当前效果{'被取消' if self.pending['nopes'] % 2 else '恢复生效'}。")

    def resolve(self, qq_id: str, rng: random.Random | None = None) -> None:
        if not self.pending:
            raise GameError("当前没有待结算的牌。")
        if qq_id != self.pending["actor"]:
            raise GameError("由出牌玩家确认结算。")
        pending = self.pending
        self.pending = None
        if pending["nopes"] % 2:
            self._record("卡牌效果已被反制。")
            return
        actor = self.player(pending["actor"])
        kind = pending["kind"]
        if kind == "attack":
            self._next(self.draws_due * 2)
        elif kind == "skip":
            self.draws_due -= 1
            if self.draws_due <= 0:
                self._next()
            else:
                self._record(f"{actor.name} 跳过一次，仍需完成 {self.draws_due} 次回合。")
        elif kind == "shuffle":
            (rng or random.SystemRandom()).shuffle(self.deck)
            self._record("抽牌堆已洗混。")
        elif kind == "see":
            self.peek[actor.qq_id] = list(reversed(self.deck[-3:]))
            self._record(f"{actor.name} 看了抽牌堆顶的三张牌。")
        elif kind == "favor":
            self.awaiting = {"kind": "favor", "actor": actor.qq_id, "target": pending["target"]}
            self._record(f"等待 {self.player(pending['target']).name} 交出一张手牌。")
        elif kind == "cat":
            target = self.player(pending["target"])
            if target.hand:
                stolen = (rng or random.SystemRandom()).choice(target.hand)
                target.hand.remove(stolen)
                actor.hand.append(stolen)
                self._record(f"{actor.name} 从 {target.name} 手中随机抽走一张牌。")
            else:
                self._record(f"{target.name} 没有手牌可抽。")
        elif kind == "pair":
            target = self.player(pending["target"])
            if target.hand:
                stolen = (rng or random.SystemRandom()).choice(target.hand)
                target.hand.remove(stolen)
                actor.hand.append(stolen)
                self._record(f"{actor.name} 从 {target.name} 手中随机抽走一张牌。")
            else:
                self._record(f"{target.name} 没有手牌可抽。")
        elif kind == "triple":
            target = self.player(pending["target"])
            found = next((id_ for id_ in target.hand if self._signature(id_) == pending["declared"]), None)
            if found:
                target.hand.remove(found)
                actor.hand.append(found)
                self._record(f"{target.name} 交出了声明的牌。")
            else:
                self._record(f"{target.name} 没有声明的牌。")
        elif kind == "five":
            retrieved = pending["retrieve"]
            self.discard.remove(retrieved)
            actor.hand.append(retrieved)
            self._record(f"{actor.name} 从弃牌堆取回一张牌。")

    def give(self, qq_id: str, card_id: str) -> None:
        if not self.awaiting or self.awaiting["kind"] != "favor" or self.awaiting["target"] != qq_id:
            raise GameError("现在无需你交牌。")
        player = self.player(qq_id)
        self._take_hand(player, card_id)
        actor = self.player(self.awaiting["actor"])
        actor.hand.append(card_id)
        self.awaiting = None
        self._record(f"{player.name} 交给 {actor.name} 一张牌。")

    def draw(self, qq_id: str) -> None:
        player = self.player(qq_id)
        if self.phase != "playing" or player != self.active:
            raise GameError("现在不是你的回合。")
        if self.pending or self.awaiting:
            raise GameError("请先完成当前卡牌效果。")
        if not self.deck:
            raise GameError("抽牌堆为空。")
        card_id = self.deck.pop()
        if CARDS[card_id]["kind"] == "bomb":
            defuse = next((id_ for id_ in player.hand if CARDS[id_]["kind"] == "defuse"), None)
            if defuse:
                player.hand.remove(defuse)
                self.discard.append(defuse)
                self.awaiting = {"kind": "defuse", "actor": qq_id, "bomb": card_id}
                self._record(f"{player.name} 抽到炸弹猫，使用了拆弹牌！请秘密决定放回位置。")
            else:
                player.alive = False
                self.discard.extend(player.hand)
                player.hand.clear()
                self.discard.append(card_id)
                self._record(f"{player.name} 抽到炸弹猫，出局！")
                self._next()
            return
        player.hand.append(card_id)
        self.draws_due -= 1
        self._record(f"{player.name} 抽了一张牌。")
        if self.draws_due <= 0:
            self._next()

    def defuse(self, qq_id: str, position: int) -> None:
        if not self.awaiting or self.awaiting["kind"] != "defuse" or self.awaiting["actor"] != qq_id:
            raise GameError("当前没有需要放回的炸弹。")
        if not 0 <= position <= len(self.deck):
            raise GameError("放回位置超出牌堆范围。")
        self.deck.insert(len(self.deck) - position, self.awaiting["bomb"])
        self.awaiting = None
        self.draws_due -= 1
        self._record(f"{self.player(qq_id).name} 把炸弹猫秘密放回抽牌堆。")
        if self.draws_due <= 0:
            self._next()

    def view(self, qq_id: str | None = None) -> dict:
        me = self.player(qq_id) if qq_id else None
        return {
            "code": self.code, "game": "exploding-kittens", "mode": self.mode, "phase": self.phase, "revision": self.revision,
            "expiresAt": int(self.created_at + 300) if self.phase == "lobby" else None,
            "players": [{"id": p.qq_id, "name": p.name, "alive": p.alive,
                         "cards": len(p.hand), "avatar": p.avatar, "claimed": bool(p.token)} for p in self.players],
            "current": self.active.qq_id if self.phase != "lobby" else None,
            "drawsDue": self.draws_due if self.phase == "playing" else 0,
            "deckCount": len(self.deck), "discard": self.discard[-1] if self.discard else None,
            "discardCount": len(self.discard), "discardCards": self.discard,
            "pending": self.pending, "awaiting": (
                {key: value for key, value in self.awaiting.items() if key != "bomb"}
                if self.awaiting else None
            ), "log": self.log[-16:],
            "me": {"id": me.qq_id, "name": me.name, "hand": me.hand, "peek": self.peek.pop(me.qq_id, [])} if me else None,
        }
