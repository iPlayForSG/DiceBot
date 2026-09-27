"""The QQ bot only forms rooms and posts the link to the web game."""

from nonebot import on_command
from nonebot.adapters import Message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent
from nonebot.params import CommandArg

from dicebot import web_bridge


HELP = (
    "QQ 组局命令（炸弹猫，2–5 人）：\n"
    "/桌游 创建 炸弹猫 [进阶]\n"
    "/桌游 加入｜离开｜开始｜状态｜结束\n"
    "游戏在网站中进行，玩家进入链接后自行选择自己的 QQ 头像和 ID。"
)

tabletop = on_command("桌游", priority=10, block=True)


@tabletop.handle()
async def handle_tabletop(event: MessageEvent, args: Message = CommandArg()) -> None:
    if not isinstance(event, GroupMessageEvent):
        await tabletop.finish("桌游组局目前只支持 QQ 群聊。")

    parts = args.extract_plain_text().strip().split()
    command = parts[0] if parts else "帮助"
    group_id, user_id = str(event.group_id), str(event.user_id)
    name = event.sender.card or event.sender.nickname or user_id

    try:
        if command in {"帮助", "help"}:
            reply = HELP
        elif command == "列表":
            reply = "当前可玩：炸弹猫（2–5 人）。发送 /桌游 创建 炸弹猫。"
        elif command == "创建":
            if len(parts) < 2 or parts[1] != "炸弹猫":
                reply = "用法：/桌游 创建 炸弹猫"
            else:
                mode = "advanced" if len(parts) > 2 and parts[2] == "进阶" else "basic"
                data = await web_bridge.create(group_id, user_id, name, mode)
                reply = f"炸弹猫{'进阶' if mode == 'advanced' else '基础'}房间已创建，房主 {name}。\n发送 /桌游 加入。\n游玩链接：{web_bridge.link(data['code'])}"
        else:
            room = await web_bridge.group(group_id)
            code = room["code"]
            players = room["players"]
            owner = players[0]["id"] if players else ""
            if command == "加入":
                await web_bridge.join(code, user_id, name)
                reply = f"{name} 已加入。游玩链接：{web_bridge.link(code)}"
            elif command == "离开":
                await web_bridge.leave(code, user_id)
                reply = f"{name} 已离开房间。"
            elif command == "开始":
                if user_id != owner:
                    reply = "只有房主可以开始游戏。"
                else:
                    await web_bridge.start(code)
                    reply = f"炸弹猫开始！请在网站选择自己的头像进入：\n{web_bridge.link(code)}"
            elif command == "状态":
                names = "、".join(player["name"] for player in players)
                reply = f"炸弹猫{'进阶' if room['mode'] == 'advanced' else '基础'}｜{room['phase']}｜{len(players)}/5 人\n玩家：{names}\n游玩链接：{web_bridge.link(code)}"
            elif command == "结束":
                if user_id != owner:
                    reply = "只有房主可以结束房间。"
                else:
                    await web_bridge.stop(code)
                    reply = "网页桌游房间已结束。"
            else:
                reply = f"未知命令：{command}\n{HELP}"
    except web_bridge.BridgeError as exc:
        reply = str(exc)

    await tabletop.finish(reply)
