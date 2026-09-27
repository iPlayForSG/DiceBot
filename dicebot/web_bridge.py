"""QQ lobby client for the separate realtime tabletop service."""

import base64
import os
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv


load_dotenv()
API_URL = os.environ.get("TABLETOP_API_URL", "http://127.0.0.1:8765").rstrip("/")
PUBLIC_URL = os.environ.get("TABLETOP_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")
ADMIN_TOKEN = os.environ.get("TABLETOP_ADMIN_TOKEN", "")


class BridgeError(Exception):
    pass


async def _request(method: str, path: str, payload: dict | None = None) -> dict:
    if not ADMIN_TOKEN:
        raise BridgeError("请先在 .env 中设置 TABLETOP_ADMIN_TOKEN。")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.request(
                method, f"{API_URL}{path}", json=payload,
                headers={"X-Tabletop-Admin": ADMIN_TOKEN},
            )
            data = response.json()
            if response.is_error:
                raise BridgeError(data.get("detail", "网页桌游服务请求失败。"))
            return data
    except httpx.RequestError as exc:
        raise BridgeError("网页桌游服务暂时不可达，请检查 TABLETOP_API_URL。") from exc


async def _avatar(qq_id: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            response = await client.get(
                "https://q1.qlogo.cn/g",
                params={"b": "qq", "nk": qq_id, "s": "100"},
            )
            response.raise_for_status()
            image = response.content
            if len(image) <= 1024 * 1024 and image.startswith((b"\xff\xd8\xff", b"\x89PNG")):
                return base64.b64encode(image).decode("ascii")
    except httpx.HTTPError:
        pass
    return None


async def _person(qq_id: str, name: str) -> dict:
    return {"qq_id": qq_id, "name": name[:24] or qq_id, "avatar_base64": await _avatar(qq_id)}


def link(code: str) -> str:
    return f"{PUBLIC_URL}/?{urlencode({'room': code})}"


async def create(group_id: str, qq_id: str, name: str, game: str = "exploding-kittens", mode: str = "basic") -> dict:
    return await _request("POST", "/api/bot/rooms", {"group_id": group_id, "player": await _person(qq_id, name), "game": game, "mode": mode})


async def group(group_id: str) -> dict:
    return await _request("GET", f"/api/bot/groups/{group_id}")


async def join(code: str, qq_id: str, name: str) -> dict:
    return await _request("POST", f"/api/bot/rooms/{code}/players", await _person(qq_id, name))


async def leave(code: str, qq_id: str) -> dict:
    return await _request("DELETE", f"/api/bot/rooms/{code}/players/{qq_id}")


async def start(code: str) -> dict:
    return await _request("POST", f"/api/bot/rooms/{code}/start")


async def stop(code: str) -> dict:
    return await _request("DELETE", f"/api/bot/rooms/{code}")


async def cancel(code: str) -> dict:
    return await _request("POST", f"/api/bot/rooms/{code}/cancel")
