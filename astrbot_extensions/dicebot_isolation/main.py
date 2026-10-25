from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from harness_bridge.client import HarnessError, HarnessService


@register('dicebot_isolation', 'DiceBot', 'Keep AI messages separate and integrate DeepSeek Harness', '1.1.0')
class MessageIsolation(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.harness = HarnessService()

    @filter.event_message_type(filter.EventMessageType.ALL, priority=1000)
    async def enforce_prefix(self, event: AstrMessageEvent):
        if event.get_platform_name() != 'aiocqhttp':
            return
        original = event.message_obj.message_str.strip()
        # 两套框架共享消息源；必须在 AI 请求前阻止桌游与普通群聊进入上下文。
        if original != '/ai' and not original.startswith('/ai '):
            event.stop_event()
            return
        if original == '/ai harness' or original.startswith('/ai harness '):
            # Harness 独占此入口，防止同一任务再被 AstrBot 的普通聊天执行一次。
            event.stop_event()
            task=original[len('/ai harness'):].strip()
            if not task:
                reply='用法：/ai harness 任务。\n支持分步分析与独立工作区的文本资料读取；模型全程使用本机反代。\n发送 /ai harness 状态 查看资料目录。'
            elif task == '状态':
                workspace=self.harness.workspace(event.unified_msg_origin,event.get_sender_id())
                reply=f'Harness 已接入本机反代。\n工具：列目录、读取文本资料。\n当前会话资料目录：{workspace}'
            else:
                try:
                    result=await self.harness.run(event.unified_msg_origin,event.get_sender_id(),task)
                    reply='[Harness · 本机反代]\n'+result.content[:3500]
                except (HarnessError,TimeoutError):
                    reply='Harness 任务未完成，请确认本机反代可用、任务不超时，且资料位于当前会话的工作区。'
                except Exception:
                    reply='Harness 运行失败，请检查独立运行日志。'
            await event.send(event.plain_result(reply))
