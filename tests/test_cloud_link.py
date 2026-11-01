import asyncio
from types import SimpleNamespace

from bot_console.cloud_link import allowed_peer,make_handler
from bot_console.network import open_http_tunnel
import pytest


def test_cloud_link_rejects_wrong_token_path_and_account():
    valid={'Authorization':'Bearer secret','X-Self-ID':'3964573597'}
    assert allowed_peer('/onebot/v11/ws',valid,'secret')
    assert not allowed_peer('/other',valid,'secret')
    assert not allowed_peer('/onebot/v11/ws',{**valid,'Authorization':'Bearer wrong'},'secret')
    assert not allowed_peer('/onebot/v11/ws',{**valid,'X-Self-ID':'999'},'secret')


def test_unauthorized_peer_cannot_open_upstream_connection():
    calls=[]
    class Incoming:
        request=SimpleNamespace(path='/onebot/v11/ws',headers={})
        async def close(self,**kwargs):calls.append(kwargs)
    def upstream(*args,**kwargs):raise AssertionError('Unauthorized connection reached upstream')
    settings=SimpleNamespace(cloud_host='45.192.248.100',cloud_proxy='http://127.0.0.1:17897')
    asyncio.run(make_handler(settings,'secret',upstream)(Incoming()))
    assert calls[0]['code']==1008


def test_proxy_connection_preserves_the_following_ssh_banner(monkeypatch):
    class Channel:
        received=b'HTTP/1.1 200 Connection established\r\n\r\nSSH-2.0-test\r\n'
        sent=b''
        def sendall(self,value):self.sent+=value
        def recv(self,size):
            value,self.received=self.received[:size],self.received[size:]
            return value
        def close(self):pass
    channel=Channel()
    monkeypatch.setattr('bot_console.network.socket.create_connection',lambda *args,**kwargs:channel)
    assert open_http_tunnel('http://127.0.0.1:17897','45.192.248.100',22) is channel
    assert channel.received.startswith(b'SSH-2.0-')
    assert channel.sent.startswith(b'CONNECT 45.192.248.100:22 HTTP/1.1')


def test_cloud_proxy_cannot_point_at_a_remote_or_credential_url():
    for proxy in ('http://example.com:17897','http://password@127.0.0.1:17897','https://127.0.0.1:17897'):
        with pytest.raises(ValueError):
            open_http_tunnel(proxy,'45.192.248.100',22)
