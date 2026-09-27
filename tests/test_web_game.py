import random

import pytest

from tabletop_server.engine import CARDS, GameError, GameRoom, Player


def game() -> GameRoom:
    room = GameRoom("TESTROOM", "123", [Player("10001", "阿明"), Player("10002", "莉莉")])
    room.start(random.Random(42))
    return room


def test_deal_and_private_hands() -> None:
    room = game()
    assert all(len(player.hand) == 8 for player in room.players)
    assert sum(CARDS[card]["kind"] == "bomb" for card in room.deck) == 1
    public = room.view()
    assert "hand" not in str(public)
    assert "hand" not in public["players"][0]
    assert room.view("10001")["me"]["hand"] == room.players[0].hand
    assert room.view("10002")["me"]["hand"] == room.players[1].hand
    with pytest.raises(GameError, match="不是你的回合"):
        room.draw("10002")


def test_nope_cancels_action_and_turn_stays() -> None:
    room = game()
    actor = room.players[0]
    opponent = room.players[1]
    action = next(card for card in CARDS if CARDS[card]["kind"] == "attack")
    nope = next(card for card in CARDS if CARDS[card]["kind"] == "nope")
    actor.hand.append(action)
    opponent.hand.append(nope)
    room.play(actor.qq_id, action)
    room.nope(opponent.qq_id, nope)
    room.resolve(actor.qq_id)
    assert room.active == actor
    assert room.draws_due == 1


def test_bomb_defuse_reinsert_is_private() -> None:
    room = game()
    actor = room.active
    bomb = next(card for card in CARDS if CARDS[card]["kind"] == "bomb" and card not in room.deck)
    room.deck.append(bomb)
    room.draw(actor.qq_id)
    assert room.awaiting and room.awaiting["kind"] == "defuse"
    assert "bomb" not in room.view()["awaiting"]
    room.defuse(actor.qq_id, 0)
    assert room.deck[-1] == bomb
    assert room.active.qq_id != actor.qq_id


def test_advanced_combinations() -> None:
    by_kind = lambda kind: [card_id for card_id, card in CARDS.items() if card["kind"] == kind]
    actor = Player("10001", "甲")
    target = Player("10002", "乙")
    room = GameRoom("ADVANCED", "123", [actor, target], mode="advanced", phase="playing")
    actor.hand = by_kind("attack")[:3] + by_kind("skip")[:1] + by_kind("see")[:1] + by_kind("favor")[:1] + by_kind("shuffle")[:1]
    target.hand = by_kind("defuse")[:1] + by_kind("nope")[:1]
    room.discard = by_kind("cat")[:1]

    room.play_combo(actor.qq_id, actor.hand[:2], target.qq_id)
    room.resolve(actor.qq_id, random.Random(1))
    assert len(actor.hand) == 6  # two discarded, one stolen
    assert len(target.hand) == 1

    # Return an attack card to construct a valid three-of-a-kind.
    actor.hand.extend(by_kind("attack")[:2])
    target.hand.extend(by_kind("skip")[:1])
    triples = [id_ for id_ in actor.hand if CARDS[id_]["kind"] == "attack"][:3]
    room.play_combo(actor.qq_id, triples, target.qq_id, declared="skip")
    room.resolve(actor.qq_id)
    assert not any(CARDS[id_]["kind"] == "skip" for id_ in target.hand)

    actor.hand.append(by_kind("attack")[3])
    unique = [next(id_ for id_ in actor.hand if CARDS[id_]["kind"] == kind) for kind in ("attack", "skip", "see", "favor", "shuffle")]
    retrieved = room.discard[0]
    room.play_combo(actor.qq_id, unique, retrieve=retrieved)
    room.resolve(actor.qq_id)
    assert retrieved in actor.hand
    assert retrieved not in room.discard
