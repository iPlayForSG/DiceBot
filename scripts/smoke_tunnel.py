"""Verify public HTTPS and WSS against the game API, then remove the test room."""

import asyncio
import json
import secrets
import sys

from dotenv import dotenv_values
import httpx
import websockets


async def main(base_url: str) -> None:
    base_url = base_url.rstrip("/")
    admin_token = dotenv_values(".env").get("TABLETOP_ADMIN_TOKEN")
    if not admin_token:
        raise RuntimeError("Missing TABLETOP_ADMIN_TOKEN in .env")
    headers = {"X-Tabletop-Admin": admin_token}
    code = None
    async with httpx.AsyncClient(timeout=25) as client:
        try:
            health = await client.get(f"{base_url}/api/health")
            health.raise_for_status()
            assert health.json()["status"] == "ok"
            created = await client.post(
                f"{base_url}/api/bot/rooms", headers=headers,
                json={"group_id": f"migration-{secrets.token_hex(8)}", "player": {"qq_id": "10005", "name": "迁移测试甲"}},
            )
            created.raise_for_status()
            code = created.json()["code"]
            joined = await client.post(
                f"{base_url}/api/bot/rooms/{code}/players", headers=headers,
                json={"qq_id": "10006", "name": "迁移测试乙"},
            )
            joined.raise_for_status()
            claimed = await client.post(f"{base_url}/api/rooms/{code}/claim", json={"qq_id": "10005"})
            claimed.raise_for_status()
            started = await client.post(f"{base_url}/api/bot/rooms/{code}/start", headers=headers)
            started.raise_for_status()
            wss = base_url.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
            async with websockets.connect(f"{wss}/ws/{code}", origin="https://iplayforsg.github.io") as socket:
                await socket.send(claimed.json()["token"])
                state = json.loads(await asyncio.wait_for(socket.recv(), timeout=10))
                assert state["code"] == code and len(state["me"]["hand"]) == 8
                assert "hand" not in state["players"][1]
            print("HTTPS, room actions, and private WSS: OK")
        finally:
            if code:
                await client.delete(f"{base_url}/api/bot/rooms/{code}", headers=headers)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/smoke_tunnel.py https://api.example.com")
    asyncio.run(main(sys.argv[1]))
