"""Realtime API used by the static GitHub Pages client and the QQ lobby bot."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import asdict
import json
import os
from pathlib import Path
import secrets
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from tabletop_server.engine import GameError, GameRoom, Player
from tabletop_server.party_games import NAMES, PartyRoom


load_dotenv()
DATA_DIR = Path(os.environ.get("TABLETOP_DATA_DIR", "data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
ROOMS_FILE = DATA_DIR / "rooms.json"
AVATAR_DIR = DATA_DIR / "avatars"
AVATAR_DIR.mkdir(exist_ok=True)
ADMIN_TOKEN = os.environ.get("TABLETOP_ADMIN_TOKEN", "")
ALLOWED_ORIGINS = [origin.strip() for origin in os.environ.get(
    "TABLETOP_ALLOWED_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000"
).split(",") if origin.strip()]

app = FastAPI(title="DiceBot tabletop service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Tabletop-Admin"],
)
rooms: dict[str, GameRoom | PartyRoom] = {}
connections: dict[str, dict[WebSocket, str]] = {}
lock = asyncio.Lock()


def _restore() -> None:
    if not ROOMS_FILE.exists():
        return
    for raw in json.loads(ROOMS_FILE.read_text(encoding="utf-8")):
        raw["players"] = [Player(**player) for player in raw["players"]]
        room = PartyRoom(**raw) if raw.get("game") in NAMES else GameRoom(**raw)
        rooms[room.code] = room


def _save() -> None:
    temporary = ROOMS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps([asdict(room) for room in rooms.values()], ensure_ascii=False), encoding="utf-8")
    temporary.replace(ROOMS_FILE)


_restore()


def _room(code: str) -> GameRoom | PartyRoom:
    room = rooms.get(code.upper())
    if room is None:
        raise HTTPException(404, "房间不存在或已经结束。")
    return room


def _admin(value: str | None) -> None:
    if not ADMIN_TOKEN:
        raise HTTPException(503, "服务端尚未设置 TABLETOP_ADMIN_TOKEN。")
    if not value or not secrets.compare_digest(value, ADMIN_TOKEN):
        raise HTTPException(403, "组局服务认证失败。")


def _member(room: GameRoom | PartyRoom, authorization: str | None) -> Player:
    token = (authorization or "").removeprefix("Bearer ")
    for player in room.players:
        if player.token and secrets.compare_digest(player.token, token):
            return player
    raise HTTPException(401, "请重新选择你的 QQ 身份。")


def _avatar(qq_id: str, content: str | None) -> bool:
    if not content:
        return False
    if not qq_id.isdecimal() or len(qq_id) > 16:
        raise HTTPException(400, "QQ ID 格式无效。")
    try:
        image = base64.b64decode(content, validate=True)
    except ValueError as exc:
        raise HTTPException(400, "头像数据无效。") from exc
    if len(image) > 1024 * 1024 or not image.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")):
        raise HTTPException(400, "头像必须是 1 MB 以下的 JPEG 或 PNG。")
    (AVATAR_DIR / qq_id).write_bytes(image)
    return True


async def _broadcast(room: GameRoom | PartyRoom) -> None:
    for websocket, token in list(connections.get(room.code, {}).items()):
        try:
            player = next((p for p in room.players if p.token and secrets.compare_digest(p.token, token)), None)
            if player is None:
                await websocket.close(code=1008)
                connections[room.code].pop(websocket, None)
                continue
            await websocket.send_json(room.view(player.qq_id))
        except Exception:
            connections[room.code].pop(websocket, None)


class BotPlayer(BaseModel):
    qq_id: str = Field(pattern=r"^\d{5,16}$")
    name: str = Field(min_length=1, max_length=24)
    avatar_base64: str | None = None


class CreateRoom(BaseModel):
    group_id: str
    player: BotPlayer
    game: Literal["exploding-kittens", "cubirds", "coup", "splendor", "avalon"] = "exploding-kittens"
    mode: str = Field(default="basic", max_length=24)


class Claim(BaseModel):
    qq_id: str


class Action(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str
    card_id: str | None = None
    second: str | None = None
    target: str | None = None
    position: int | None = None
    cards: list[str] | None = None
    declared: str | None = None
    retrieve: str | None = None


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/bot/rooms")
async def create_room(payload: CreateRoom, x_tabletop_admin: str | None = Header(default=None)) -> dict[str, str]:
    _admin(x_tabletop_admin)
    allowed = {
        "exploding-kittens": {"basic", "advanced"}, "cubirds": {"basic"},
        "splendor": {"basic"}, "avalon": {"basic", "advanced"},
        "coup": {"basic", "reformation", "ks-bureaucrat", "ks-speculator"},
    }
    if payload.mode not in allowed[payload.game]:
        raise HTTPException(400, "所选游戏模式无效。")
    async with lock:
        if any(room.group_id == payload.group_id for room in rooms.values()):
            raise HTTPException(409, "本群已有网页桌游房间。")
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        while code in rooms:
            code = "".join(secrets.choice(alphabet) for _ in range(8))
        player = Player(payload.player.qq_id, payload.player.name)
        player.avatar = _avatar(player.qq_id, payload.player.avatar_base64)
        room = (GameRoom(code, payload.group_id, [player], mode=payload.mode)
                if payload.game == "exploding-kittens" else
                PartyRoom(code, payload.group_id, [player], payload.game, mode=payload.mode))
        room._record(f"{player.name} 创建了{NAMES.get(payload.game, '炸弹猫')}房间。")
        rooms[code] = room
        _save()
    return {"code": code}


@app.post("/api/bot/rooms/{code}/players")
async def add_player(code: str, payload: BotPlayer, x_tabletop_admin: str | None = Header(default=None)) -> dict[str, str]:
    _admin(x_tabletop_admin)
    async with lock:
        room = _room(code)
        try:
            room.add_player(payload.qq_id, payload.name)
        except GameError as exc:
            raise HTTPException(400, str(exc)) from exc
        room.player(payload.qq_id).avatar = _avatar(payload.qq_id, payload.avatar_base64)
        _save()
        await _broadcast(room)
    return {"status": "joined"}


@app.get("/api/bot/groups/{group_id}")
async def group_room(group_id: str, x_tabletop_admin: str | None = Header(default=None)) -> dict[str, Any]:
    _admin(x_tabletop_admin)
    room = next((room for room in rooms.values() if room.group_id == group_id), None)
    if room is None:
        raise HTTPException(404, "本群还没有网页桌游房间。")
    return room.view()


@app.delete("/api/bot/rooms/{code}/players/{qq_id}")
async def remove_player(code: str, qq_id: str, x_tabletop_admin: str | None = Header(default=None)) -> dict[str, str]:
    _admin(x_tabletop_admin)
    async with lock:
        room = _room(code)
        if room.phase != "lobby":
            raise HTTPException(400, "游戏已经开始。")
        player = room.player(qq_id)
        room.players.remove(player)
        if room.players:
            room._record(f"{player.name} 离开了房间。")
            await _broadcast(room)
        else:
            del rooms[room.code]
        _save()
    return {"status": "left"}


@app.post("/api/bot/rooms/{code}/start")
async def start_room(code: str, x_tabletop_admin: str | None = Header(default=None)) -> dict[str, str]:
    _admin(x_tabletop_admin)
    async with lock:
        room = _room(code)
        try:
            room.start()
        except GameError as exc:
            raise HTTPException(400, str(exc)) from exc
        _save()
        await _broadcast(room)
    return {"status": "playing"}


@app.delete("/api/bot/rooms/{code}")
async def close_room(code: str, x_tabletop_admin: str | None = Header(default=None)) -> dict[str, str]:
    _admin(x_tabletop_admin)
    async with lock:
        room = _room(code)
        del rooms[room.code]
        _save()
        for websocket in list(connections.get(room.code, {})):
            await websocket.close(code=1001)
        connections.pop(room.code, None)
    return {"status": "closed"}


@app.get("/api/rooms/{code}")
async def get_room(code: str) -> dict[str, Any]:
    return _room(code).view()


@app.post("/api/rooms/{code}/claim")
async def claim_room(code: str, payload: Claim) -> dict[str, str]:
    async with lock:
        room = _room(code)
        try:
            player = room.player(payload.qq_id)
        except GameError as exc:
            raise HTTPException(400, str(exc)) from exc
        # Friends explicitly choose their own QQ identity; selecting it again
        # transfers that seat to the new browser and revokes the previous token.
        player.token = secrets.token_urlsafe(32)
        _save()
        await _broadcast(room)
    return {"token": player.token}


@app.get("/api/rooms/{code}/me")
async def my_room(code: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    room = _room(code)
    return room.view(_member(room, authorization).qq_id)


@app.post("/api/rooms/{code}/actions")
async def act(code: str, payload: Action, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    async with lock:
        room = _room(code)
        player = _member(room, authorization)
        try:
            if isinstance(room, PartyRoom):
                room.action(player.qq_id, payload.model_dump(exclude_none=True))
            elif payload.type == "draw":
                room.draw(player.qq_id)
            elif payload.type == "play":
                room.play(player.qq_id, payload.card_id or "", payload.target, payload.second)
            elif payload.type == "combo":
                room.play_combo(player.qq_id, payload.cards or [], payload.target, payload.declared, payload.retrieve)
            elif payload.type == "nope":
                room.nope(player.qq_id, payload.card_id or "")
            elif payload.type == "resolve":
                room.resolve(player.qq_id)
            elif payload.type == "give":
                room.give(player.qq_id, payload.card_id or "")
            elif payload.type == "defuse":
                room.defuse(player.qq_id, payload.position if payload.position is not None else -1)
            else:
                raise GameError("未知行动。")
        except GameError as exc:
            raise HTTPException(400, str(exc)) from exc
        _save()
        await _broadcast(room)
        return room.view(player.qq_id)


@app.get("/api/avatars/{qq_id}")
async def get_avatar(qq_id: str) -> FileResponse:
    if not qq_id.isdecimal() or len(qq_id) > 16:
        raise HTTPException(404)
    path = AVATAR_DIR / qq_id
    if not path.exists():
        raise HTTPException(404)
    media_type = "image/png" if path.read_bytes().startswith(b"\x89PNG") else "image/jpeg"
    return FileResponse(path, media_type=media_type)


@app.websocket("/ws/{code}")
async def room_socket(websocket: WebSocket, code: str) -> None:
    room = rooms.get(code.upper())
    if not room:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        token = await asyncio.wait_for(websocket.receive_text(), timeout=8)
    except (asyncio.TimeoutError, WebSocketDisconnect):
        await websocket.close(code=1008)
        return
    player = next((p for p in room.players if p.token and secrets.compare_digest(p.token, token)), None)
    if not player:
        await websocket.close(code=1008)
        return
    connections.setdefault(room.code, {})[websocket] = token
    await websocket.send_json(room.view(player.qq_id))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connections[room.code].pop(websocket, None)
