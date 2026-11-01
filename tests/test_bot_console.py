import asyncio
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from bot_console.app import Controller, Settings, create_app, password_hash


class FakeController(Controller):
    def __init__(self, settings):
        super().__init__(settings)
        self.flags = {'tabletop': False, 'ai': False}
        self.calls = []
        self.fail_ai = False
        self.cloud_reachable = True

    async def _actual(self):
        return {key:{'enabled':value, 'reachable':self.cloud_reachable if key=='tabletop' else True} for key,value in self.flags.items()}

    async def _set(self, bot, enabled):
        self.calls.append((bot, enabled))
        if bot == 'ai' and enabled and self.fail_ai:
            raise RuntimeError('AI failed')
        self.flags[bot] = enabled

    async def snapshot(self, force=False):
        return {'bots':await self._actual()}


@pytest.fixture
def console(tmp_path):
    settings = Settings(password_hash('test-console-password'), 'test', 'key', 'hosts', 'proxy', state_dir=tmp_path)
    controller = FakeController(settings)
    client = TestClient(create_app(settings, controller))
    return client, controller


def authenticate(client):
    result=client.post('/api/login',json={'password':'test-console-password'},headers={'Origin':'http://testserver'})
    assert result.status_code==200


def test_console_requires_login_for_private_state_and_switches(console):
    client, controller = console
    assert client.get('/api/status').status_code==401
    assert client.post('/api/mode',json={'mode':'off'},headers={'Origin':'http://testserver'}).status_code==401
    assert controller.calls==[]


def test_cross_origin_cannot_login_or_switch(console):
    client, controller = console
    assert client.post('/api/login',json={'password':'test-console-password'},headers={'Origin':'http://untrusted.example'}).status_code==403
    authenticate(client)
    assert client.post('/api/mode',json={'mode':'both'},headers={'Origin':'http://untrusted.example'}).status_code==403
    assert controller.calls==[]


def test_logout_invalidates_the_existing_session(console):
    client, _ = console
    authenticate(client)
    old_cookie=client.cookies.get('bot_console')
    assert client.get('/api/status').status_code==200
    assert client.post('/api/logout',json={},headers={'Origin':'http://testserver'}).status_code==200
    client.cookies.set('bot_console',old_cookie)
    assert client.get('/api/status').status_code==401


def test_unknown_mode_never_reaches_service_commands(console):
    client, controller = console
    authenticate(client)
    assert client.post('/api/mode',json={'mode':'both; shutdown'},headers={'Origin':'http://testserver'}).status_code==422
    assert controller.calls==[]


def test_partial_mode_change_rolls_back_completed_operations(console):
    _, controller = console
    controller.fail_ai=True
    with pytest.raises(RuntimeError):
        asyncio.run(controller.set_mode('both'))
    assert controller.flags=={'tabletop':False,'ai':False}
    assert controller.calls==[('tabletop',True),('ai',True),('tabletop',False)]
    assert not controller.state_file.exists()


def test_switching_mode_preserves_independent_states(console):
    client, controller = console
    authenticate(client)
    for mode, expected in [('both',(True,True)),('ai',(False,True)),('tabletop',(True,False)),('off',(False,False))]:
        result=client.post('/api/mode',json={'mode':mode},headers={'Origin':'http://testserver'})
        assert result.status_code==200
        assert tuple(controller.flags.values())==expected
    assert controller.state_file.exists()


def test_login_rate_limit_is_enforced(console):
    client, _ = console
    for _ in range(5):
        assert client.post('/api/login',json={'password':'wrong'},headers={'Origin':'http://testserver'}).status_code==401
    assert client.post('/api/login',json={'password':'wrong'},headers={'Origin':'http://testserver'}).status_code==429


def test_ai_switch_is_independent_when_cloud_is_unreachable(console):
    client,controller=console
    controller.cloud_reachable=False
    authenticate(client)
    for enabled in (True,False):
        response=client.post('/api/bots/ai',json={'enabled':enabled},headers={'Origin':'http://testserver'})
        assert response.status_code==200
        assert controller.flags['ai']==enabled
    assert all(name=='ai' for name,_ in controller.calls)


def test_global_mode_does_not_guess_unreachable_cloud_state(console):
    client,controller=console
    controller.cloud_reachable=False
    authenticate(client)
    assert client.post('/api/mode',json={'mode':'both'},headers={'Origin':'http://testserver'}).status_code==503
    assert controller.calls==[]


def test_unknown_bot_cannot_select_arbitrary_service(console):
    client,controller=console
    authenticate(client)
    assert client.post('/api/bots/other-service',json={'enabled':True},headers={'Origin':'http://testserver'}).status_code==422
    assert controller.calls==[]
