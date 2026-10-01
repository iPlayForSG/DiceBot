from dataclasses import asdict
import json
import time

from fastapi.testclient import TestClient
import pytest
from starlette.websockets import WebSocketDisconnect

from tabletop_server import app as service
from tabletop_server.engine import GameRoom, Player
from tabletop_server.party_games import PartyRoom, LIMITS as PARTY_LIMITS
from tabletop_server.workshop_room import WorkshopRoom, LIMITS as WORKSHOP_LIMITS


@pytest.fixture
def isolated_service(monkeypatch, tmp_path):
    service.rooms.clear()
    service.connections.clear()
    monkeypatch.setattr(service, "ADMIN_TOKEN", "test-admin")
    monkeypatch.setattr(service, "ROOMS_FILE", tmp_path / "rooms.json")
    monkeypatch.setattr(service, "CLEANUP_INTERVAL_SECONDS", 0.02)
    yield {"X-Tabletop-Admin":"test-admin"}
    service.rooms.clear()
    service.connections.clear()


def started_room(game="coup"):
    count=PARTY_LIMITS.get(game, WORKSHOP_LIMITS.get(game, (2,5)))[0]
    players=[Player(str(10001+i),f"玩家{i}",token=f"token-{i}",claim_code=f"CLAIM{i+1:05}") for i in range(count)]
    if game=="exploding-kittens": room=GameRoom("IDLE0001","group",players)
    elif game in PARTY_LIMITS: room=PartyRoom("IDLE0001","group",players,game)
    else: room=WorkshopRoom("IDLE0001","group",players,game)
    room.start()
    service.rooms[room.code]=room
    service._save()
    return room


@pytest.mark.parametrize("game", ["exploding-kittens",*PARTY_LIMITS,*WORKSHOP_LIMITS])
def test_all_game_types_release_group_after_one_hour(game, isolated_service):
    room=started_room(game)
    room.last_activity_at=time.time()-3601
    with TestClient(service.app) as client:
        assert client.get(f"/api/rooms/{room.code}").status_code==404
        assert client.get("/api/bot/groups/group",headers=isolated_service).status_code==404
        created=client.post("/api/bot/rooms",headers=isolated_service,json={
            "group_id":"group","player":{"qq_id":"10001","name":"甲"}})
        assert created.status_code==200
        assert room.code not in service.rooms
        assert all(raw["code"]!=room.code for raw in json.loads(service.ROOMS_FILE.read_text(encoding="utf8")))


def test_cleanup_closes_idle_websocket_without_any_requests(isolated_service):
    room=started_room()
    with TestClient(service.app) as client:
        with client.websocket_connect(f"/ws/{room.code}") as socket:
            socket.send_text(room.players[0].token)
            socket.receive_json()
            room.last_activity_at=time.time()-3601
            deadline=time.monotonic()+1
            while room.code in service.rooms and time.monotonic()<deadline:
                time.sleep(0.02)
            assert room.code not in service.rooms
            assert room.code not in service.connections
            with pytest.raises(WebSocketDisconnect) as error:
                socket.receive_json()
            assert error.value.code==1001
            assert "一小时" in error.value.reason


def test_only_successful_game_actions_extend_the_idle_window(isolated_service):
    room=started_room()
    room.last_activity_at=time.time()-3500
    previous=room.last_activity_at
    with TestClient(service.app) as client:
        assert client.get(f"/api/rooms/{room.code}").status_code==200
        assert client.get(f"/api/rooms/{room.code}/me",headers={"Authorization":"Bearer token-0"}).status_code==200
        claimed=client.post(f"/api/rooms/{room.code}/claim",json={"claim_code":room.players[0].claim_code})
        assert claimed.status_code==200
        auth={"Authorization":"Bearer "+claimed.json()["token"]}
        with client.websocket_connect(f"/ws/{room.code}") as socket:
            socket.send_text(claimed.json()["token"])
            socket.receive_json()
        assert client.post(f"/api/rooms/{room.code}/actions",headers=auth,json={"type":"invalid"}).status_code==400
        assert room.last_activity_at==previous
        before=time.time()
        assert client.post(f"/api/rooms/{room.code}/actions",headers=auth,json={"type":"declare","move":"income"}).status_code==200
        assert room.last_activity_at>=before
        stored=json.loads(service.ROOMS_FILE.read_text(encoding="utf8"))[0]["last_activity_at"]
        service.rooms.clear()
        assert not service._restore()
        assert service.rooms[room.code].last_activity_at==stored


def test_start_resets_timer_and_old_snapshots_get_one_migration_window(isolated_service):
    room=started_room()
    raw=asdict(room)
    raw.pop("last_activity_at")
    service.ROOMS_FILE.write_text(json.dumps([raw]),encoding="utf8")
    service.rooms.clear()
    before=time.time()
    assert service._restore()
    assert service.rooms[room.code].last_activity_at>=before
    service._save()
    saved=service.rooms[room.code].last_activity_at
    service.rooms.clear()
    assert not service._restore()
    assert service.rooms[room.code].last_activity_at==saved
    service.rooms.clear()
    lobby=GameRoom("LOBBY001","group",[Player("10001","甲"),Player("10002","乙")],created_at=time.time()-240,last_activity_at=time.time()-240)
    service.rooms[lobby.code]=lobby
    with TestClient(service.app) as client:
        before=time.time()
        assert client.post(f"/api/bot/rooms/{lobby.code}/start",headers=isolated_service).status_code==200
        assert lobby.last_activity_at>=before
