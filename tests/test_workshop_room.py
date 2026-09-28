import pytest

from tabletop_server.engine import GameError, Player
from tabletop_server.workshop_room import WorkshopRoom, NAMES, LIMITS, CATALOGS


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


def test_sushi_chopsticks_take_two_and_pass_on():
    r = room("sushi-go")
    first, second = (p.qq_id for p in r.players)
    with pytest.raises(GameError):
        r.action(first, {"type": "pick_two", "cards": r.state["hands"][first][:2]})
    chopsticks = next(c for c in CATALOGS["sushi-go"][0] if r._card(c)["name"] == "筷子")
    for zone in [r.state["deck"], *r.state["hands"].values()]:
        if chopsticks in zone:
            zone.remove(chopsticks)
    r.state["table"][first].append(chopsticks)
    choices = r.state["hands"][first][:2]
    r.action(first, {"type": "pick_two", "cards": choices})
    assert r.view()["players"][0]["table"] == []
    r.action(second, {"type": "pick", "card_id": r.state["hands"][second][0]})
    assert r.state["table"][first] == choices
    assert chopsticks in r.state["hands"][second]


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
    assert r.view()["players"][0]["wall"] == [color]


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


def test_sushi_preserves_pudding_between_rounds():
    r = room("sushi-go")
    pudding = next(c for c in CATALOGS["sushi-go"][0] if r._card(c)["name"] == "布丁")
    if pudding in r.state["deck"]:
        r.state["deck"].remove(pudding)
    r.state["table"][r.players[0].qq_id].append(pudding)
    for p in r.players:
        r.state["hands"][p.qq_id] = []
    r.action(r.players[0].qq_id, {"type": "next_round"})
    assert r.view()["players"][0]["puddings"] == 1


def test_love_letter_discard_is_public():
    r = room("love-letter")
    actor = r.players[0].qq_id
    card = r.state["hands"][actor][0]
    r.action(actor, {"type": "discard", "card_id": card})
    assert r.view()["discardCards"][0]["id"] == card


def test_once_upon_a_time_third_edition_two_player_deal():
    r = room("once-upon-a-time")
    hand = r.state["hands"][r.players[0].qq_id]
    assert sum(r._card(card)["group"] == "story" for card in hand) == 9
    assert sum(r._card(card)["group"] == "ending" for card in hand) == 1
