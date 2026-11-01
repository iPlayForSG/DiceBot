from __future__ import annotations

import socket
from urllib.parse import urlsplit


def open_http_tunnel(proxy_url: str, destination: str, port: int, timeout=10):
    proxy=urlsplit(proxy_url)
    if proxy.scheme!='http' or proxy.hostname not in ('127.0.0.1','localhost') or not proxy.port or proxy.username or proxy.password or proxy.query or proxy.fragment:
        raise ValueError('云端连接只允许使用本机 HTTP 代理。')
    channel=socket.create_connection((proxy.hostname,proxy.port),timeout=timeout)
    try:
        target=f'{destination}:{port}'
        channel.sendall(f'CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n'.encode('ascii'))
        header=bytearray()
        while not header.endswith(b'\r\n\r\n'):
            value=channel.recv(1)
            if not value or len(header)>16384:raise OSError('代理握手未完成。')
            header.extend(value)
        status=bytes(header).split(b'\r\n',1)[0].split(b' ',2)
        if len(status)<2 or status[1]!=b'200':raise OSError('代理拒绝云端连接。')
        # 代理仅承载 TCP；SSH 的远端主机密钥仍由原有固定记录校验。
        return channel
    except Exception:
        channel.close()
        raise
