"""Run AstrBot as a standalone scheduled task with private local state."""
import asyncio
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
runtime = ROOT / '.local-tools/astrbot/runtime'
runtime.mkdir(parents=True, exist_ok=True)
os.environ['ASTRBOT_ROOT'] = str(runtime)
os.chdir(runtime)
sys.path.insert(0, str(runtime))
log = (runtime / 'managed.log').open('a', encoding='utf-8', buffering=1)
sys.stdout = log
sys.stderr = log
credentials = json.loads((ROOT / '.local-tools/bot-console/credentials.json').read_text(encoding='utf-8'))
proxy = json.loads(Path(credentials['proxy_config']).read_text(encoding='utf-8-sig'))
# API 密钥归反代配置所有；启动时读取，避免多份明文配置失去同步。
os.environ['DICEBOT_PROXY_API_KEY'] = proxy['api_key']

from astrbot.core import LogBroker, LogManager, db_helper, logger
from astrbot.core.initial_loader import InitialLoader
import astrbot

async def main():
    broker = LogBroker()
    LogManager.set_queue_handler(logger, broker)
    loader = InitialLoader(db_helper, broker)
    loader.webui_dir = str(Path(astrbot.__file__).parent / 'dashboard/dist')
    await loader.start()

if __name__ == '__main__':
    asyncio.run(main())
