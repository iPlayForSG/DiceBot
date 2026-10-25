from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register


@register('dicebot_isolation', 'DiceBot', 'Keep AI messages separate from tabletop commands', '1.0.0')
class MessageIsolation(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.event_message_type(filter.EventMessageType.ALL, priority=1000)
    async def enforce_prefix(self, event: AstrMessageEvent):
        if event.get_platform_name() != 'aiocqhttp':
            return
        original = event.message_obj.message_str.strip()
        # 两套框架共享消息源；必须在 AI 请求前阻止桌游与普通群聊进入上下文。
        if original != '/ai' and not original.startswith('/ai '):
            event.stop_event()
