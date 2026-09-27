"""The QQ bot only forms rooms and posts the link to the web game."""

from nonebot import on_command
from nonebot.adapters import Message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent
from nonebot.params import CommandArg
import time

from dicebot import web_bridge


GAMES = {
    "炸弹猫": ("exploding-kittens", "炸弹猫", "2–5"),
    "方·鸟": ("cubirds", "方·鸟", "2–5"),
    "方鸟": ("cubirds", "方·鸟", "2–5"),
    "CuBirds": ("cubirds", "方·鸟", "2–5"),
    "政变": ("coup", "政变", "2–10"),
    "璀璨宝石": ("splendor", "璀璨宝石", "2–4"),
    "阿瓦隆": ("avalon", "阿瓦隆", "5–10"),
}
GAME_NAMES = {game: name for game, name, _ in GAMES.values()}
GAME_LIMITS = {game: limit for game, _, limit in GAMES.values()}
HELP = (
    "QQ 组局命令：\n"
    "/桌游 列表\n"
    "/桌游 创建 <游戏名> [进阶/扩展/KS/KS投机者]\n"
    "/桌游 加入 <房间码>｜离开｜开始｜状态｜取消｜结束\n"
    "身份码仅由 Bot 私聊发送。请确认群设置已开启“允许群成员私聊”。"
)

tabletop = on_command("桌游", priority=10, block=True)


@tabletop.handle()
async def handle_tabletop(bot: Bot, event: MessageEvent, args: Message = CommandArg()) -> None:
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
            reply = "当前可玩：炸弹猫（2–5 人）、方·鸟（2–5 人）、政变（2–10 人）、璀璨宝石（2–4 人）、阿瓦隆（5–10 人）。\n发送 /桌游 创建 <游戏名>。"
        elif command == "创建":
            if len(parts) < 2 or parts[1] not in GAMES:
                reply = "用法：/桌游 创建 炸弹猫｜方·鸟｜政变｜璀璨宝石｜阿瓦隆"
            else:
                game, game_name, limit = GAMES[parts[1]]
                variant = parts[2] if len(parts) > 2 else ""
                mode = "advanced" if game in {"exploding-kittens", "avalon"} and variant == "进阶" else "reformation" if game == "coup" and variant == "扩展" else "ks-bureaucrat" if game == "coup" and variant == "KS" else "ks-speculator" if game == "coup" and variant == "KS投机者" else "basic"
                data = await web_bridge.create(group_id, user_id, name, game, mode)
                try:
                    await bot.send_private_msg(user_id=int(user_id), message=(
                        f"{game_name}房间 {data['code']} 的身份码：{data['claim_code']}\n"
                        f"游玩链接：{web_bridge.link(data['code'])}\n请在网页输入身份码认领座位，不要在群里转发身份码。"
                    ))
                except Exception:
                    try:
                        await web_bridge.stop(data["code"])
                        reply = "组局未完成：Bot 无法私聊房主。请确认本群已开启“允许群成员私聊”，然后重新创建。"
                    except web_bridge.BridgeError:
                        reply = f"Bot 无法私聊房主，房间 {data['code']} 可能仍占用；请确认本群已开启“允许群成员私聊”，房主可发送 /桌游 取消 {data['code']}。"
                else:
                    reply = (
                        f"{game_name}{'KS 角色包' if mode.startswith('ks-') else '扩展' if mode == 'reformation' else '进阶' if mode == 'advanced' else ''}房间已创建，房主 {name}。\n"
                        f"房间码：{data['code']}｜支持 {limit} 人。\n"
                        f"发送 /桌游 加入 {data['code']}。5 分钟内未开始会自动取消；房主可发送 /桌游 取消 {data['code']}。\n"
                        f"身份码已私聊房主。请确认本群已开启“允许群成员私聊”。\n"
                        f"游玩链接：{web_bridge.link(data['code'])}"
                    )
        else:
            room = await web_bridge.group(group_id)
            code = room["code"]
            game = room.get("game", "exploding-kittens")
            game_name = GAME_NAMES.get(game, "炸弹猫")
            players = room["players"]
            owner = players[0]["id"] if players else ""
            if command == "加入":
                if len(parts) != 2:
                    reply = "用法：/桌游 加入 <房间码>。房间码见建房消息。"
                elif parts[1].upper() != code:
                    reply = "房间码不属于本群当前组局，请检查建房消息。"
                else:
                    data = await web_bridge.join(code, user_id, name)
                    try:
                        await bot.send_private_msg(user_id=int(user_id), message=(
                            f"{game_name}房间 {code} 的身份码：{data['claim_code']}\n"
                            f"游玩链接：{web_bridge.link(code)}\n请在网页输入身份码认领座位，不要在群里转发身份码。"
                        ))
                    except Exception:
                        if data["status"] == "joined":
                            try:
                                await web_bridge.leave(code, user_id)
                            except web_bridge.BridgeError:
                                pass
                        reply = "加入未完成：Bot 无法私聊你。请确认本群已开启“允许群成员私聊”，然后重新发送带房间码的加入命令。"
                    else:
                        reply = f"{name} {'已加入' if data['status'] == 'joined' else '已在房间中'}，身份码已私聊发送。游玩链接：{web_bridge.link(code)}"
            elif command == "离开":
                await web_bridge.leave(code, user_id)
                reply = f"{name} 已离开房间。"
            elif command == "开始":
                if user_id != owner:
                    reply = "只有房主可以开始游戏。"
                else:
                    await web_bridge.start(code)
                    reply = f"{game_name}开始！请打开网站并输入 Bot 私聊给你的身份码：\n{web_bridge.link(code)}"
            elif command == "状态":
                names = "、".join(player["name"] for player in players)
                remaining = max(0, room["expiresAt"] - int(time.time())) if room.get("expiresAt") else None
                expiry = f"｜距自动取消 {remaining} 秒" if remaining is not None else ""
                reply = f"{game_name}｜{room['phase']}｜{len(players)}/{GAME_LIMITS.get(game, '5').split('–')[-1]} 人{expiry}\n玩家：{names}\n游玩链接：{web_bridge.link(code)}"
            elif command == "取消":
                if user_id != owner:
                    reply = "只有房主可以取消未开局房间。"
                elif len(parts) > 1 and parts[1].upper() != code:
                    reply = "房间码不匹配，取消未执行。"
                else:
                    await web_bridge.cancel(code)
                    reply = f"房间 {code} 已取消，可以重新组局。"
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
