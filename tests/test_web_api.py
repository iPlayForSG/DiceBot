from fastapi.testclient import TestClient
import json
import pytest
import time
from starlette.websockets import WebSocketDisconnect

from tabletop_server import app as service


def test_lobby_to_private_game_api(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(service, "ADMIN_TOKEN", "test-token")
    monkeypatch.setattr(service, "ROOMS_FILE", tmp_path / "rooms.json")
    monkeypatch.setattr(service, "AVATAR_DIR", tmp_path)
    service.rooms.clear()
    admin = {"X-Tabletop-Admin": "test-token"}
    with TestClient(service.app) as client:
        created = client.post("/api/bot/rooms", headers=admin, json={
            "group_id": "99", "player": {"qq_id": "10001", "name": "阿明"}
        })
        assert created.status_code == 200
        code = created.json()["code"]
        joined = client.post(f"/api/bot/rooms/{code}/players", headers=admin, json={
            "qq_id": "10002", "name": "莉莉"
        })
        assert joined.status_code == 200
        assert client.post(f"/api/rooms/{code}/claim", json={"qq_id": "10001"}).status_code == 422
        assert client.post(f"/api/rooms/{code}/claim", json={"claim_code": "AAAAAAAAAA"}).status_code == 400
        public_before = client.get(f"/api/rooms/{code}").json()
        assert created.json()["claim_code"] not in str(public_before)
        assert joined.json()["claim_code"] not in str(public_before)
        token = client.post(f"/api/rooms/{code}/claim", json={"claim_code": created.json()["claim_code"]}).json()["token"]
        second_token = client.post(f"/api/rooms/{code}/claim", json={"claim_code": joined.json()["claim_code"]}).json()["token"]
        with client.websocket_connect(f"/ws/{code}") as first_socket, client.websocket_connect(f"/ws/{code}") as second_socket:
            first_socket.send_text(token)
            second_socket.send_text(second_token)
            first_socket.receive_json()
            second_socket.receive_json()
            assert client.post(f"/api/bot/rooms/{code}/start", headers=admin).status_code == 200
            resend = client.post(f"/api/bot/rooms/{code}/players", headers=admin, json={
                "qq_id": "10002", "name": "莉莉"
            })
            assert resend.json()["status"] == "already_joined"
            assert resend.json()["claim_code"] == joined.json()["claim_code"]
            assert client.post(f"/api/bot/rooms/{code}/players", headers=admin, json={
                "qq_id": "10003", "name": "新玩家"
            }).status_code == 400
            first_view = first_socket.receive_json()
            second_view = second_socket.receive_json()
            assert first_view["me"]["id"] == "10001"
            assert second_view["me"]["id"] == "10002"
            assert first_view["me"]["hand"] != second_view["me"]["hand"]
            assert "hand" not in first_view["players"][1]
        public = client.get(f"/api/rooms/{code}").json()
        private = client.get(f"/api/rooms/{code}/me", headers={"Authorization": f"Bearer {token}"}).json()
        assert public["me"] is None
        assert len(private["me"]["hand"]) == 8
        assert client.post(f"/api/rooms/{code}/actions", json={"type": "draw"}).status_code == 401
        assert client.post(f"/api/rooms/{code}/actions", headers={"Authorization": f"Bearer {token}"}, json={"type": "draw"}).status_code == 200
        assert (tmp_path / "rooms.json").exists()
    service.rooms.clear()


def test_lobby_auto_expires_and_owner_can_cancel(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(service, "ADMIN_TOKEN", "test-token")
    monkeypatch.setattr(service, "ROOMS_FILE", tmp_path / "rooms.json")
    service.rooms.clear()
    admin = {"X-Tabletop-Admin": "test-token"}
    payload = {"group_id": "expiry-group", "player": {"qq_id": "10001", "name": "甲"}}
    with TestClient(service.app) as client:
        first = client.post("/api/bot/rooms", headers=admin, json=payload).json()["code"]
        assert client.get(f"/api/rooms/{first}").json()["expiresAt"]
        service.rooms[first].created_at -= 301
        assert client.get(f"/api/rooms/{first}").status_code == 404
        second = client.post("/api/bot/rooms", headers=admin, json=payload)
        assert second.status_code == 200  # Expired room no longer blocks the group.
        code = second.json()["code"]
        assert first not in service.rooms
        assert client.post(f"/api/bot/rooms/{code}/cancel", headers=admin).status_code == 200
        assert client.get(f"/api/rooms/{code}").status_code == 404
    service.rooms.clear()


def test_idle_lobby_cleanup_runs_without_requests(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(service, "ADMIN_TOKEN", "test-token")
    monkeypatch.setattr(service, "ROOMS_FILE", tmp_path / "rooms.json")
    monkeypatch.setattr(service, "CLEANUP_INTERVAL_SECONDS", 0.02)
    service.rooms.clear()
    with TestClient(service.app) as client:
        created = client.post("/api/bot/rooms", headers={"X-Tabletop-Admin": "test-token"}, json={
            "group_id": "idle-group", "player": {"qq_id": "10001", "name": "甲"}
        })
        code = created.json()["code"]
        token = client.post(f"/api/rooms/{code}/claim", json={
            "claim_code": created.json()["claim_code"]
        }).json()["token"]
        with client.websocket_connect(f"/ws/{code}") as socket:
            socket.send_text(token)
            socket.receive_json()
            service.rooms[code].created_at -= 301
            deadline = time.monotonic() + 1
            while code in service.rooms and time.monotonic() < deadline:
                time.sleep(0.02)
            assert code not in service.rooms
            with pytest.raises(WebSocketDisconnect):
                socket.receive_json()
        assert client.get(f"/api/rooms/{code}").status_code == 404
    service.rooms.clear()


def test_old_lobby_requires_new_identity_code_after_restore(monkeypatch, tmp_path) -> None:
    path = tmp_path / "rooms.json"
    path.write_text(json.dumps([{
        "code": "OLDROOM1", "group_id": "old-group", "phase": "lobby",
        "players": [{"qq_id": "10001", "name": "甲", "token": "legacy-browser-token"}],
    }]), encoding="utf-8")
    monkeypatch.setattr(service, "ROOMS_FILE", path)
    service.rooms.clear()
    assert service._restore()
    service._save()
    room = service.rooms["OLDROOM1"]
    assert room.players[0].token is None
    assert room.players[0].claim_code is None
    assert room.created_at <= time.time()
    assert json.loads(path.read_text(encoding="utf-8"))[0]["created_at"]
    service.rooms.clear()
