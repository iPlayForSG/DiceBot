from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.local-tools/harness'


def session_key(origin: str, sender: str) -> str:
    return hashlib.sha256((origin + '\0' + sender).encode()).hexdigest()[:32]


@dataclass
class HarnessResult:
    content: str
    tools: list[str]
    elapsed: float


class HarnessError(RuntimeError):
    pass


def validate_proxy_route(proxy: dict):
    target=urlsplit(proxy.get('base_url',''))
    # 用户明确要求只用本机反代；配置异常时拒绝启动，不尝试官方端点。
    if target.scheme!='http' or target.hostname not in ('127.0.0.1','localhost') or target.port!=8788 or target.path.rstrip('/')!='/v1' or target.username or target.password or target.query or target.fragment:
        raise HarnessError('Harness 只允许使用本机 8788 端口的反代接口。')


class HarnessClient:
    def __init__(self, workspace: Path, home: Path, proxy: dict):
        self.workspace, self.home, self.proxy = workspace, home, proxy
        self.pending = {}
        self.notifications = []
        self.errors = deque(maxlen=40)
        self.process = None
        self.reader = None
        self.stderr = None
        self.sequence = 0

    async def start(self):
        validate_proxy_route(self.proxy)
        node = shutil.which('node') or 'C:/Program Files/nodejs/node.exe'
        executable = RUNTIME / 'node_modules/@deepseek-ai/dsh/lib/bin.js'
        if not executable.is_file():
            raise HarnessError('Harness 运行环境尚未安装。')
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.home.mkdir(parents=True, exist_ok=True)
        patch = self.home / 'qq-profile.patch.yml'
        template = (ROOT / 'harness_bridge/profile.patch.yml').read_text(encoding='utf-8')
        patch.write_text(template.replace('"__DICEBOT_WORKSPACE_PLUGIN__"',
            json.dumps((ROOT / 'harness_bridge/workspace-tools.mjs').as_posix())), encoding='utf-8')
        # 子进程只接收运行所需环境及模型凭据，不继承控制台和云端部署秘密。
        environment = {key:value for key,value in os.environ.items() if key.upper() in {
            'SYSTEMROOT','WINDIR','COMSPEC','PATH','PATHEXT','TEMP','TMP','USERPROFILE','LOCALAPPDATA','APPDATA'}}
        environment.update({
            'DSH_HOME': str(self.home), 'DSH_TELEMETRY':'0',
            'DICEBOT_HARNESS_API_KEY': self.proxy['api_key'],
            'DICEBOT_HARNESS_BASE_URL': self.proxy['base_url'],
            'DICEBOT_HARNESS_MODEL': self.proxy['model'],
            'DICEBOT_HARNESS_PACKAGE_ROOT': str(RUNTIME),
            'DICEBOT_HARNESS_WORKSPACE': str(self.workspace),
        })
        self.process = await asyncio.create_subprocess_exec(node, str(executable), '--profile', 'sdk-minimal',
            '--patch', str(patch), cwd=self.workspace, env=environment,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0), limit=2*1024*1024)
        self.reader = asyncio.create_task(self._read())
        self.stderr = asyncio.create_task(self._errors())
        await self.rpc('initialize', {'cwd':str(self.workspace), 'provider':'dicebot-proxy',
                                    'model':self.proxy['model'], 'maxTokens':2048}, timeout=45)
        if any('disabling profile plugin row' in line for line in self.errors):
            raise HarnessError('Harness 工具配置加载失败，已停止执行。')

    async def _read(self):
        try:
            while line := await self.process.stdout.readline():
                message = json.loads(line)
                if 'id' in message:
                    future = self.pending.get(str(message['id']))
                    if future and not future.done():
                        if 'error' in message:
                            future.set_exception(HarnessError(str(message['error'].get('message','Harness 请求失败'))))
                        else:
                            future.set_result(message.get('result'))
                elif 'method' in message:
                    self.notifications.append(message)
        except Exception as error:
            self.errors.append(type(error).__name__)
        finally:
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(HarnessError('Harness 子进程连接已结束。'))

    async def _errors(self):
        while line := await self.process.stderr.readline():
            self.errors.append(line.decode('utf-8',errors='replace').replace(self.proxy['api_key'],'[REDACTED]').strip())

    async def rpc(self, method: str, params=None, timeout=150):
        self.sequence += 1
        identity = str(self.sequence)
        future = asyncio.get_running_loop().create_future()
        self.pending[identity] = future
        try:
            payload = json.dumps({'jsonrpc':'2.0','id':identity,'method':method,'params':params}) + '\n'
            self.process.stdin.write(payload.encode())
            await self.process.stdin.drain()
            return await asyncio.wait_for(future,timeout)
        finally:
            self.pending.pop(identity,None)

    async def run(self, prompt: str, identity='main'):
        started = time.monotonic()
        marker = self.home / 'session-created.json'
        if marker.exists():
            await self.rpc('session/resume', {'sessionId':identity})
        await self.rpc('session/prompt', {'sessionId':identity,'contentBlocks':[{'type':'text','text':prompt}]})
        marker.write_text(json.dumps({'sessionId':identity}), encoding='utf-8')
        await self.rpc('session/wait', {'sessionId':identity})
        return self._result(started)

    def _result(self, started):
        events = [item.get('params',{}).get('event',{}) for item in self.notifications if item.get('method')=='session.event']
        endings=[event.get('data',{}).get('reason',{}).get('kind') for event in events if event.get('type')=='turn/end']
        if not endings or endings[-1] != 'completed':
            raise HarnessError('Harness 本次任务未完成，请缩短任务后重试。')
        # 返回正式提交的助手消息，工具轨迹保留用于核实实际执行而非猜测能力。
        assistant = [event for event in events if event.get('type') in ('assistant/message','message/assistant')]
        content = ''
        if assistant:
            data=assistant[-1].get('data',{})
            blocks=data.get('content',data.get('message',{}).get('content',[]))
            if isinstance(blocks,str):content=blocks
            else:content=''.join(block.get('text','') for block in blocks if block.get('type')=='text')
        tools=[]
        for event in events:
            if 'tool' in event.get('type',''):
                data=event.get('data',{})
                name=data.get('name') or data.get('toolName') or data.get('call',{}).get('name')
                if name and name not in tools:tools.append(name)
        if not content:
            raise HarnessError('Harness 没有返回最终文本，请检查运行事件。')
        return HarnessResult(content,tools,round(time.monotonic()-started,2))

    async def close(self):
        if self.process and self.process.returncode is None:
            try:
                await self.rpc('shutdown',None,timeout=5)
            except Exception:
                pass
            try:
                await asyncio.wait_for(self.process.wait(),5)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        for task in (self.reader,self.stderr):
            if task and not task.done():task.cancel()


class HarnessService:
    def __init__(self):
        self.lock=asyncio.Lock()

    def workspace(self, origin: str, sender: str):
        key=session_key(origin,sender)
        workspace=RUNTIME/'workspaces'/key
        workspace.mkdir(parents=True,exist_ok=True)
        return workspace

    async def run(self, origin: str, sender: str, prompt: str):
        if self.lock.locked():
            raise HarnessError('已有 Harness 任务正在运行，请稍候。')
        if not prompt.strip() or len(prompt)>2000:
            raise HarnessError('请提供不超过 2000 字的任务。')
        async with self.lock:
            key=session_key(origin,sender)
            config=json.loads((ROOT/'.local-tools/bot-console/credentials.json').read_text(encoding='utf-8'))
            proxy=json.loads(Path(config['proxy_config']).read_text(encoding='utf-8-sig'))
            client=HarnessClient(self.workspace(origin,sender),RUNTIME/'homes'/key,proxy)
            try:
                await client.start()
                return await asyncio.wait_for(client.run(prompt),150)
            except Exception as error:
                details=str(error)+'\n'+'\n'.join(client.errors)
                client.home.mkdir(parents=True,exist_ok=True)
                (client.home/'last-error.log').write_text(details.replace(proxy['api_key'],'[REDACTED]'),encoding='utf-8')
                raise
            finally:
                await client.close()
