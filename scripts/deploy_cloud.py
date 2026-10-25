"""Publish the development checkout to the configured Linux host over SSH."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import tarfile
import time
import paramiko

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='45.192.248.100')
    parser.add_argument('--user', default='root')
    parser.add_argument('--public-url', default='https://45.192.248.100:8443')
    parser.add_argument('--key', type=Path, default=ROOT / '.local-tools/cloud-deploy/id_ed25519')
    args = parser.parse_args()
    state = ROOT / '.local-tools/cloud-deploy'
    state.mkdir(parents=True, exist_ok=True)
    subprocess.run(['uv', 'export', '--quiet', '--locked', '--no-dev', '--no-emit-project',
                    '--format', 'requirements-txt', '--output-file', 'deployment/cloud-requirements.txt'],
                   cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    release_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    package = state / f'{release_id}.tar.gz'
    # 发布白名单排除本机工具、QQ 登录缓存和私钥，避免越过开发/运行环境边界。
    with tarfile.open(package, 'w:gz') as archive:
        for name in ('bot.py', 'dicebot', 'tabletop_server', 'web', 'deployment', 'pyproject.toml', 'uv.lock', 'README.md'):
            archive.add(ROOT / name, arcname=name,
                        filter=lambda info: None if '__pycache__' in Path(info.name).parts else info)
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    print(f'Upload {package.stat().st_size / 1048576:.1f} MiB', flush=True)
    client = paramiko.SSHClient()
    client.load_host_keys(str(state / 'known_hosts'))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(args.host, username=args.user, key_filename=str(args.key),
                   look_for_keys=False, allow_agent=False, timeout=20)
    try:
        remote = f'/opt/dicebot/releases/{release_id}'
        _, out, _ = client.exec_command(f'mkdir -p {shlex.quote(remote)}')
        if out.channel.recv_exit_status():
            raise RuntimeError('Cannot prepare release directory')
        with client.open_sftp() as sftp:
            last = [0.0]
            def progress(done, total):
                if time.monotonic() - last[0] >= 10 or done == total:
                    print(f'Upload {done / total:.0%}', flush=True)
                    last[0] = time.monotonic()
            sftp.put(str(package), remote + '/package.tar.gz', callback=progress)
        command = (
            f'cd {shlex.quote(remote)} && '
            f'echo {shlex.quote(digest + "  package.tar.gz")} | sha256sum -c - && '
            'tar --no-same-owner -xzf package.tar.gz && rm package.tar.gz && '
            f'PUBLIC_URL={shlex.quote(args.public_url)} python3 -c '
            + shlex.quote("import os,json;from pathlib import Path;Path('web/config.js').write_text('window.TABLETOP_API_URL = '+json.dumps(os.environ['PUBLIC_URL'])+';'+chr(10))")
            + f' && bash deployment/linux/activate.sh {shlex.quote(remote)}'
        )
        _, out, _ = client.exec_command(command)
        out.channel.set_combine_stderr(True)
        for line in out:
            print(line.rstrip(), flush=True)
        if out.channel.recv_exit_status():
            raise RuntimeError('Release activation failed')
        print(json.dumps({'release': remote, 'publicURL': args.public_url, 'sha256': digest}))
    finally:
        client.close()

if __name__ == '__main__':
    main()
