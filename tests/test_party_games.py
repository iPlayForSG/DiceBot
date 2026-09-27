import random

import pytest

from tabletop_server.engine import GameError, Player
from tabletop_server.party_games import PartyRoom, SPLENDOR_CARDS, bird


def room(game: str, count: int, mode: str = "basic") -> PartyRoom:
    result = PartyRoom("TESTROOM", "123", [Player(str(10000 + i), f"玩家{i}") for i in range(count)], game, mode)
    result.start(random.Random(42))
    return result


@pytest.mark.parametrize("game,count", [("cubirds", 2), ("coup", 2), ("splendor", 2), ("avalon", 5)])
def test_setup_keeps_private_information_private(game: str, count: int) -> None:
    game_room = room(game, count)
    game_room.players[0].claim_code = "ABCDEFGHJK"
    public = game_room.view()
    personal = game_room.view("10000")
    assert public["game"] == game
    assert public["me"] is None
    assert "deck" not in public["state"]
    assert personal["me"]["id"] == "10000"
    assert "hand" not in public["players"][0]
    assert "ABCDEFGHJK" not in str(public)
    if game == "avalon":
        assert "roles" not in public["state"]
        assert personal["me"]["role"]
    if game == "splendor":
        assert isinstance(public["state"]["reserved"]["10000"], int)


def test_cubirds_place_and_end_turn() -> None:
    game_room = room("cubirds", 2)
    actor = game_room.players[0]
    species = bird(actor.hand[0])["species"]
    game_room.action(actor.qq_id, {"type": "place", "species": species, "row": 0, "side": "left"})
    assert game_room.state["stage"] == "flock"
    with pytest.raises(GameError):
        game_room.action(game_room.players[1].qq_id, {"type": "end_turn"})
    game_room.action(actor.qq_id, {"type": "end_turn"})
    assert game_room.state["current"] == 1


def test_splendor_reserve_and_tokens() -> None:
    game_room = room("splendor", 2)
    actor = game_room.players[0]
    card_id = game_room.state["market"]["1"][0]
    assert SPLENDOR_CARDS[card_id]["tier"] == 1
    game_room.action(actor.qq_id, {"type": "reserve", "card": card_id, "tier": 1})
    assert card_id in game_room.state["reserved"][actor.qq_id]
    assert game_room.state["hold"][actor.qq_id]["j"] == 1
    second = game_room.players[1]
    game_room.action(second.qq_id, {"type": "take", "colors": ["w", "u", "g"]})
    assert game_room.state["hold"][second.qq_id]["w"] == 1
    with pytest.raises(GameError):
        game_room.action(actor.qq_id, {"type": "take", "colors": ["r"], "returns": ["b"]})


def test_splendor_noble_choice_blocks_other_actions() -> None:
    game_room = room("splendor", 2)
    actor = game_room.players[0]
    choice = game_room.state["nobles"][0]
    game_room.state["pending_noble"] = game_room.state["nobles"][:2]
    with pytest.raises(GameError, match="先从可访问的贵族"):
        game_room.action(actor.qq_id, {"type": "take", "colors": ["w", "u", "g"]})
    game_room.action(actor.qq_id, {"type": "claim_noble", "noble": choice})
    assert choice in game_room.state["claimed"][actor.qq_id]
    assert choice not in game_room.state["nobles"]
    assert game_room.state["current"] == 1


def test_avalon_secret_votes_and_quest() -> None:
    game_room = room("avalon", 5, "advanced")
    ids = [player.qq_id for player in game_room.players]
    game_room.action(ids[0], {"type": "propose", "team": ids[:2]})
    game_room.action(ids[0], {"type": "team_vote", "vote": "approve"})
    assert game_room.view()["state"]["votes"] == {ids[0]: True}
    for qq_id in ids[1:]:
        game_room.action(qq_id, {"type": "team_vote", "vote": "approve"})
    assert game_room.state["stage"] == "quest_vote"
    game_room.action(ids[0], {"type": "quest_vote", "vote": "success"})
    assert game_room.view()["state"]["quest_votes"] == {ids[0]: True}
    game_room.action(ids[1], {"type": "quest_vote", "vote": "success"})
    assert game_room.state["results"] == [True]


def test_coup_coin_action_and_private_cards() -> None:
    game_room = room("coup", 2)
    actor = game_room.players[0]
    assert len(actor.hand) == 2
    game_room.action(actor.qq_id, {"type": "declare", "move": "income"})
    game_room.action(actor.qq_id, {"type": "resolve"})
    assert game_room.state["coins"][actor.qq_id] == 3
    assert game_room.state["current"] == 1


@pytest.mark.parametrize("mode,move", [("ks-bureaucrat", "bribe"), ("ks-speculator", "invest")])
def test_coup_ks_replacement_roles(mode: str, move: str) -> None:
    game_room = room("coup", 2, mode)
    actor, target = game_room.players
    assert "弄臣" in game_room.state["deck"] + actor.hand + target.hand
    game_room.action(actor.qq_id, {"type": "declare", "move": move, "target": target.qq_id})
    game_room.action(actor.qq_id, {"type": "resolve"})
    assert game_room.state["coins"][actor.qq_id] == 4
    if move == "bribe":
        assert game_room.state["coins"][target.qq_id] == 3


def test_coup_jester_disorder_preserves_private_hand_counts() -> None:
    game_room = room("coup", 2, "ks-bureaucrat")
    actor, target = game_room.players
    game_room.action(actor.qq_id, {"type": "declare", "move": "disorder", "target": target.qq_id})
    game_room.action(actor.qq_id, {"type": "resolve"})
    assert len(actor.hand) == 4 and len(target.hand) == 1
    choices = actor.hand[:2]
    game_room.action(actor.qq_id, {"type": "disorder_finish", "to_target": choices[0], "to_deck": choices[1]})
    assert len(actor.hand) == 2 and len(target.hand) == 2
    assert "deck" not in game_room.view()["state"]
