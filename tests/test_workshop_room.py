import pytest

from tabletop_server.engine import GameError, Player
from tabletop_server.workshop_room import WorkshopRoom, NAMES, LIMITS


def room(game, count=2):
    players = [Player(str(10000 + i), f"玩家{i}") for i in range(count)]
    result = WorkshopRoom("TESTROOM", "99", players, game)
    result.start()
    return result


@pytest.mark.parametrize("game", NAMES)
def test_all_workshop_games_start_without_exposing_private_cards(game):
    r = room(game, LIMITS[game][0])
    public, private = r.view(), r.view("10000")
    assert public["game"] == game
    assert public["me"] is None
    assert private["me"]["id"] == "10000"
    assert "hand" not in public["players"][0]
    assert (r.players[0].claim_code or "secret") not in str(public)


def test_sushi_pick_is_secret_until_everyone_picks():
    r = room("sushi-go")
    first, second = (p.qq_id for p in r.players)
    card_a = r.state["hands"][first][0]
    card_b = r.state["hands"][second][0]
    r.action(first, {"type": "pick", "card_id": card_a})
    assert r.view()["players"][0]["table"] == []
    assert r.view(first)["picked"]
    with pytest.raises(GameError):
        r.action(first, {"type": "pick", "card_id": r.state["hands"][first][0]})
    r.action(second, {"type": "pick", "card_id": card_b})
    assert r.state["table"][first] == [card_a]
    assert r.state["table"][second] == [card_b]
    assert len(r.state["hands"][first]) == 9


def test_azul_factory_draft_and_pattern_line():
    r = room("azul")
    actor = r.players[0].qq_id
    color = r.state["factories"][0][0]
    count = r.state["factories"][0].count(color)
    r.action(actor, {"type": "tile", "source": 0, "color": color})
    assert r.state["player_tiles"][actor].count(color) == count
    assert r.state["factories"][0] == []
    r.action(actor, {"type": "place_tile", "color": color, "row": 0})
    r.action(actor, {"type": "resolve_pattern", "row": 0})
    assert r.state["wall"][actor] == [color]


def test_flip_city_uses_personal_deck_and_shared_supply():
    r = room("flip-city")
    actor = r.players[0].qq_id
    assert r.view(actor)["deckCount"] == 9
    supply = r.view(actor)["market"]
    assert supply
    r.action(actor, {"type": "draw"})
    assert len(r.state["table"][actor]) == 1
    assert r.view()["players"][0]["table"]
    r.action(actor, {"type": "buy", "card_id": supply[0]["card"]["id"]})
    assert len(r.state["personal_discard"][actor]) == 1
    r.action(actor, {"type": "turn"})
    assert len(r.state["personal_discard"][actor]) == 2
