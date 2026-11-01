from __future__ import annotations

import asyncio
import hmac
import json
import logging
from pathlib import Path
import ssl

import certifi
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from bot_console.app import ROOT, STATE, Settings

ACCOUNT='3964573597'
PATH='/onebot/v11/ws'
logger=logging.getLogger('dicebot-cloud-link')


def allowed_peer(path: str, headers, token: str):
    return path==PATH and hmac.compare_digest(headers.get('Authorization',''),'Bearer '+token) and headers.get('X-Self-ID')==ACCOUNT


def make_handler(settings: Settings, token: str, connector=connect):
    async def handle(incoming):
        if not allowed_peer(incoming.request.path,incoming.request.headers,token):
            await incoming.close(code=1008,reason='Unauthorized OneBot peer')
            return
        try:
            # 只转接此账号到固定云端；TLS 校验和 OneBot 鉴权均保持启用。
            async with connector(f'wss://{settings.cloud_host}:8443'+PATH,proxy=settings.cloud_proxy,
                ssl=ssl.create_default_context(cafile=certifi.where()),
                additional_headers={'Authorization':'Bearer '+token,'X-Self-ID':ACCOUNT,'X-Client-Role':'Universal'},
                open_timeout=20,close_timeout=5) as remote:
                logger.info('Cloud OneBot connection established')
                async def forward(source,destination):
                    try:
                        async for message in source:
                            await destination.send(message)
                    finally:
                        await destination.close()
                await asyncio.gather(forward(incoming,remote),forward(remote,incoming),return_exceptions=True)
        except Exception as error:
            logger.warning('Cloud connection unavailable: %s',type(error).__name__)
            await incoming.close(code=1013,reason='Cloud temporarily unavailable')
    return handle


async def main():
    settings=Settings.load()
    if not settings.cloud_proxy:raise RuntimeError('Cloud proxy is not configured.')
    values=dict(line.split('=',1) for line in (ROOT/'.env.cloud').read_text(encoding='utf-8').splitlines() if '=' in line and not line.startswith('#'))
    token=values['ONEBOT_ACCESS_TOKEN'].strip()
    logging.basicConfig(filename=STATE/'cloud-link.log',level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    async with serve(make_handler(settings,token),'127.0.0.1',18380,ping_interval=30,max_size=2*1024*1024):
        logger.info('Local cloud link ready at 127.0.0.1:18380')
        await asyncio.Future()


if __name__=='__main__':
    asyncio.run(main())
