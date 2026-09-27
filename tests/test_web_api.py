from fastapi.testclient import TestClient

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
        assert client.post(f"/api/bot/rooms/{code}/players", headers=admin, json={
            "qq_id": "10002", "name": "莉莉"
        }).status_code == 200
        token = client.post(f"/api/rooms/{code}/claim", json={"qq_id": "10001"}).json()["token"]
        assert client.post(f"/api/bot/rooms/{code}/start", headers=admin).status_code == 200
        public = client.get(f"/api/rooms/{code}").json()
        private = client.get(f"/api/rooms/{code}/me", headers={"Authorization": f"Bearer {token}"}).json()
        assert public["me"] is None
        assert len(private["me"]["hand"]) == 8
        assert client.post(f"/api/rooms/{code}/actions", json={"type": "draw"}).status_code == 401
        assert client.post(f"/api/rooms/{code}/actions", headers={"Authorization": f"Bearer {token}"}, json={"type": "draw"}).status_code == 200
        assert (tmp_path / "rooms.json").exists()
    service.rooms.clear()
