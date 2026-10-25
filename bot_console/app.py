from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import subprocess
import time
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import httpx
import paramiko
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.local-tools' / 'bot-console'
MODES = {'tabletop': (True, False), 'ai': (False, True), 'both': (True, True), 'off': (False, False)}


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 240_000).hex()
    return salt + ':' + digest


def verify_password(password: str, value: str) -> bool:
    return hmac.compare_digest(password_hash(password, value.split(':')[0]), value)


@dataclass
class Settings:
    password: str
    cloud_host: str
    cloud_key: str
    cloud_known_hosts: str
    proxy_config: str
    state_dir: Path = STATE
    task: str = 'DiceBot AstrBot'

    @classmethod
    def load(cls):
        values = json.loads((STATE / 'settings.json').read_text(encoding='utf-8'))
        return cls(**values)


class Controller:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.lock = asyncio.Lock()
        self.test_lock = asyncio.Lock()
        self.cache: dict = {}
        self.cache_until = 0.0
        self.events = deque(maxlen=30)
        self.state_file = settings.state_dir / 'state.json'

    def record(self, message: str):
        self.events.appendleft({'time': datetime.now().astimezone().strftime('%H:%M:%S'), 'message': message})

    def _ssh(self, command: str) -> str:
        client = paramiko.SSHClient()
        client.load_host_keys(self.settings.cloud_known_hosts)
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        try:
            client.connect(self.settings.cloud_host, username='root', key_filename=self.settings.cloud_key,
                           allow_agent=False, look_for_keys=False, timeout=6, auth_timeout=6)
            _, out, _ = client.exec_command(command, timeout=15)
            out.channel.set_combine_stderr(True)
            output = out.read().decode('utf-8', errors='replace').strip()
            if out.channel.recv_exit_status():
                raise RuntimeError('云端服务操作失败，请检查 SSH 连接与服务状态。')
            return output
        finally:
            client.close()

    def _task(self, action: str) -> str:
        scripts = {
            'status': "$t=Get-ScheduledTask -TaskName 'DiceBot AstrBot' -ErrorAction Stop; @{running=($t.State -eq 'Running');enabled=($t.State -ne 'Disabled')} | ConvertTo-Json -Compress",
            'start': "Enable-ScheduledTask -TaskName 'DiceBot AstrBot' | Out-Null; Start-ScheduledTask -TaskName 'DiceBot AstrBot'",
            'stop': "Stop-ScheduledTask -TaskName 'DiceBot AstrBot'; Disable-ScheduledTask -TaskName 'DiceBot AstrBot' | Out-Null",
        }
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                                 "$ErrorActionPreference='Stop';" + scripts[action]],
                                capture_output=True, timeout=15,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise RuntimeError('AstrBot 启动任务不可用，请检查本机任务计划程序。')
        return result.stdout.decode('utf-8-sig', errors='replace').strip()

    async def _actual(self):
        # 控制端只允许固定服务和固定任务，网页输入不得成为远端命令。
        results = await asyncio.gather(
            asyncio.to_thread(self._ssh, 'systemctl is-active dicebot-bot.service || true'),
            asyncio.to_thread(self._task, 'status'), return_exceptions=True,
        )
        cloud, local = results
        return {
            'tabletop': {'enabled': cloud == 'active', 'reachable': not isinstance(cloud, Exception),
                         'detail': '云端独立进程', 'error': str(cloud) if isinstance(cloud, Exception) else None},
            'ai': {'enabled': bool(json.loads(local).get('running')) if isinstance(local, str) else False,
                   'reachable': not isinstance(local, Exception), 'detail': '本机独立环境',
                   'error': str(local) if isinstance(local, Exception) else None},
        }

    async def snapshot(self, force=False):
        if not force and time.monotonic() < self.cache_until:
            return self.cache
        bots = await self._actual()
        proxy = {'ready': False, 'model': 'deepseek-v4.1-flash', 'base': 'http://127.0.0.1:8788/v1'}
        napcat = False
        async with httpx.AsyncClient(timeout=3, trust_env=False, follow_redirects=True) as client:
            try:
                config = json.loads(Path(self.settings.proxy_config).read_text(encoding='utf-8-sig'))
                proxy.update(model=config['model'], base=config['base_url'])
                result = await client.get(config['base_url'].removesuffix('/v1') + '/health',
                                          headers={'Authorization': 'Bearer ' + config['api_key']})
                proxy['ready'] = result.status_code == 200 and result.json().get('accounts_ready', 0) > 0
            except (OSError, ValueError, httpx.HTTPError, KeyError):
                pass
            try:
                napcat = (await client.get('http://127.0.0.1:6099/')).status_code == 200
            except httpx.HTTPError:
                pass
        enabled = (bots['tabletop']['enabled'], bots['ai']['enabled'])
        mode = next((key for key, flags in MODES.items() if flags == enabled), 'off')
        self.cache = {'bots': bots, 'mode': mode, 'proxy': proxy, 'napcat': napcat,
                      'events': list(self.events), 'checkedAt': datetime.now(timezone.utc).isoformat()}
        self.cache_until = time.monotonic() + 4
        return self.cache

    async def _set(self, bot: str, enabled: bool):
        if bot == 'tabletop':
            verb = 'enable --now' if enabled else 'disable --now'
            await asyncio.to_thread(self._ssh, f'systemctl {verb} dicebot-bot.service')
        else:
            await asyncio.to_thread(self._task, 'start' if enabled else 'stop')
            if enabled:
                for _ in range(60):
                    try:
                        _, writer = await asyncio.wait_for(asyncio.open_connection('127.0.0.1', 6199), timeout=1)
                        writer.close()
                        await writer.wait_closed()
                        break
                    except (OSError, TimeoutError):
                        await asyncio.sleep(1)
                else:
                    await asyncio.to_thread(self._task, 'stop')
                    raise RuntimeError('AstrBot 未能启动，请检查独立运行日志。')
            else:
                for _ in range(40):
                    try:
                        _, writer = await asyncio.wait_for(asyncio.open_connection('127.0.0.1', 6199), timeout=1)
                        writer.close()
                        await writer.wait_closed()
                        await asyncio.sleep(0.25)
                    except (OSError, TimeoutError):
                        break
                else:
                    raise RuntimeError('AstrBot 尚未完全退出，请稍候再启用。')

    async def set_mode(self, mode: str):
        async with self.lock:
            before = await self._actual()
            if not all(bot['reachable'] for bot in before.values()):
                raise RuntimeError('未能取得两端状态，未执行切换。请检查连接后重试。')
            targets = dict(zip(('tabletop', 'ai'), MODES[mode]))
            changed = []
            try:
                # 先启动新选择，再关闭旧选择；切换失败时恢复已完成的部分。
                for enabled in (True, False):
                    for bot, target in targets.items():
                        if target == enabled and before[bot]['enabled'] != target:
                            await self._set(bot, target)
                            changed.append(bot)
                self.state_file.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.state_file.with_suffix('.tmp')
                temporary.write_text(json.dumps({'mode': mode}), encoding='utf-8')
                temporary.replace(self.state_file)
                self.record({'tabletop':'已选择仅桌游', 'ai':'已选择仅 AI', 'both':'已开启两个 Bot', 'off':'已关闭两个 Bot 的 QQ 响应'}[mode])
            except Exception:
                for bot in reversed(changed):
                    try:
                        await self._set(bot, before[bot]['enabled'])
                    except Exception:
                        self.record('部分操作恢复失败，请核对实际运行状态。')
                self.cache_until = 0
                raise
            self.cache_until = 0
            return await self.snapshot(force=True)

    async def test_proxy(self, prompt: str):
        if self.test_lock.locked():
            raise RuntimeError('已有反代测试进行中，请稍候。')
        async with self.test_lock:
            values = json.loads(Path(self.settings.proxy_config).read_text(encoding='utf-8-sig'))
            started = time.monotonic()
            async with httpx.AsyncClient(timeout=90, trust_env=False) as client:
                response = await client.post(values['base_url'].rstrip('/') + '/chat/completions',
                    headers={'Authorization': 'Bearer ' + values['api_key']},
                    json={'model': values['model'], 'messages':[{'role':'user','content':prompt}],
                          'max_tokens':256, 'reasoning_effort':'low', 'stream':False})
                if response.status_code != 200:
                    raise RuntimeError(f'反代返回 HTTP {response.status_code}，请查看网关日志。')
                result = response.json()
            content = result.get('choices', [{}])[0].get('message', {}).get('content') or ''
            self.record('DeepSeek 反代测试完成')
            self.cache_until = 0
            return {'content': content[:4000], 'model': result.get('model', values['model']),
                    'elapsed': round(time.monotonic()-started, 2), 'tokens': result.get('usage', {}).get('total_tokens')}


class Login(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class Mode(BaseModel):
    mode: str


class Prompt(BaseModel):
    prompt: str = Field(default='只回复：连接成功', min_length=1, max_length=500)


def create_app(settings: Settings | None = None, controller: Controller | None = None):
    settings = settings or Settings.load()
    controller = controller or Controller(settings)
    app = FastAPI(title='Bot 控制室', docs_url=None, redoc_url=None, openapi_url=None)
    sessions: dict[str, float] = {}
    failures = deque()

    def origin(request: Request):
        parsed = urlsplit(request.headers.get('origin', ''))
        if parsed.scheme != request.url.scheme or parsed.netloc != request.url.netloc:
            raise HTTPException(403, '请从控制台页面发起操作。')

    def authenticated(request: Request):
        token = request.cookies.get('bot_console', '')
        if sessions.get(token, 0) < time.time():
            sessions.pop(token, None)
            raise HTTPException(401, '请登录控制台。')

    @app.middleware('http')
    async def local_boundary(request: Request, call_next):
        if request.headers.get('host', '').split(':')[0] not in ('127.0.0.1', 'localhost', 'testserver'):
            return Response('Invalid host', status_code=400)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
        return response

    @app.get('/')
    async def index():
        return FileResponse(Path(__file__).parent/'web/index.html')

    @app.post('/api/login', dependencies=[Depends(origin)])
    async def login(value: Login, response: Response):
        now = time.monotonic()
        while failures and failures[0] < now - 60:
            failures.popleft()
        if len(failures) >= 5:
            raise HTTPException(429, '尝试次数过多，请一分钟后重试。')
        if not verify_password(value.password, settings.password):
            failures.append(now)
            raise HTTPException(401, '密码不正确。')
        token = secrets.token_urlsafe(32)
        sessions[token] = time.time() + 8*3600
        response.set_cookie('bot_console', token, httponly=True, samesite='strict', max_age=8*3600)
        return {'ok': True}

    @app.post('/api/logout', dependencies=[Depends(origin)])
    async def logout(request: Request, response: Response):
        sessions.pop(request.cookies.get('bot_console', ''), None)
        response.delete_cookie('bot_console')
        return {'ok': True}

    @app.get('/api/status', dependencies=[Depends(authenticated)])
    async def status():
        return await controller.snapshot()

    @app.post('/api/mode', dependencies=[Depends(authenticated), Depends(origin)])
    async def mode(value: Mode):
        if value.mode not in MODES:
            raise HTTPException(422, '未知的运行模式。')
        try:
            return await controller.set_mode(value.mode)
        except Exception as error:
            raise HTTPException(503, str(error)) from None

    @app.post('/api/proxy/test', dependencies=[Depends(authenticated), Depends(origin)])
    async def test(value: Prompt):
        try:
            return await controller.test_proxy(value.prompt)
        except Exception:
            raise HTTPException(503, '反代测试失败，请确认网关在线、账号可用且当前没有其他请求。') from None

    app.mount('/static', StaticFiles(directory=Path(__file__).parent/'web'), name='static')
    return app
