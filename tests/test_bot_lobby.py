import asyncio

import nonebot
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message

nonebot.init()
from dicebot.plugins import tabletop as lobby  # noqa: E402


def event(user_id: int = 10002) -> GroupMessageEvent:
    message = Message("/桌游")
    return GroupMessageEvent.model_validate({
        "time": 1, "self_id": 10000, "post_type": "message", "sub_type": "normal",
        "user_id": user_id, "message_type": "group", "message_id": 1,
        "message": message, "original_message": message, "raw_message": "/桌游",
        "font": 0, "sender": {"nickname": "测试玩家"}, "group_id": 123,
    })


def room() -> dict:
    return {"code": "ABCDEFGH", "game": "coup", "mode": "basic", "phase": "lobby",
            "expiresAt": 9999999999, "players": [{"id": "10001", "name": "房主"}]}


def capture_reply(monkeypatch) -> list[str]:
    replies = []

    async def finish(message):
        replies.append(message)

    monkeypatch.setattr(lobby.tabletop, "finish", finish)
    return replies


def test_join_requires_room_code_and_sends_claim_code_privately(monkeypatch) -> None:
    replies = capture_reply(monkeypatch)
    calls = []

    async def group(_):
        return room()

    async def join(*args):
        calls.append(args)
        return {"status": "joined", "claim_code": "PRIVATEXYZ"}

    class Bot:
        async def send_private_msg(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(lobby.web_bridge, "group", group)
    monkeypatch.setattr(lobby.web_bridge, "join", join)
    asyncio.run(lobby.handle_tabletop(Bot(), event(), Message("加入")))
    assert "<房间码>" in replies[-1]
    assert not calls

    asyncio.run(lobby.handle_tabletop(Bot(), event(), Message("加入 ABCDEFGH")))
    assert calls[0] == ("ABCDEFGH", "10002", "测试玩家")
    assert calls[1]["user_id"] == 10002
    assert "PRIVATEXYZ" in calls[1]["message"]
    assert "PRIVATEXYZ" not in replies[-1]


def test_failed_private_message_rolls_back_new_join(monkeypatch) -> None:
    replies = capture_reply(monkeypatch)
    rolled_back = []

    async def group(_):
        return room()

    async def join(*_):
        return {"status": "joined", "claim_code": "PRIVATEXYZ"}

    async def leave(*args):
        rolled_back.append(args)

    class Bot:
        async def send_private_msg(self, **_):
            raise RuntimeError("private messages blocked")

    monkeypatch.setattr(lobby.web_bridge, "group", group)
    monkeypatch.setattr(lobby.web_bridge, "join", join)
    monkeypatch.setattr(lobby.web_bridge, "leave", leave)
    asyncio.run(lobby.handle_tabletop(Bot(), event(), Message("加入 ABCDEFGH")))
    assert rolled_back == [("ABCDEFGH", "10002")]
    assert "允许群成员私聊" in replies[-1]
    assert "PRIVATEXYZ" not in replies[-1]


def test_owner_can_cancel_unstarted_room(monkeypatch) -> None:
    replies = capture_reply(monkeypatch)
    cancelled = []

    async def group(_):
        return room()

    async def cancel(code):
        cancelled.append(code)

    monkeypatch.setattr(lobby.web_bridge, "group", group)
    monkeypatch.setattr(lobby.web_bridge, "cancel", cancel)
    asyncio.run(lobby.handle_tabletop(object(), event(10001), Message("取消 ABCDEFGH")))
    assert cancelled == ["ABCDEFGH"]
    assert "已取消" in replies[-1]

    asyncio.run(lobby.handle_tabletop(object(), event(10002), Message("取消 ABCDEFGH")))
    assert cancelled == ["ABCDEFGH"]
    assert "只有房主" in replies[-1]
