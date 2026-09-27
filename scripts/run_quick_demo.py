"""Run the QQ bot, game API and a temporary Cloudflare tunnel together.

The tunnel URL changes on every restart. This script updates the GitHub Actions
variable and dispatches the Pages workflow when a saved GitHub credential exists.
Keep this terminal open while people play. Ctrl+C stops all child processes.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
GITHUB_REPOSITORY = "iPlayForSG/DiceBot"
PROCESS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def git_credential() -> str:
    result = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        text=True, capture_output=True, timeout=15,
        env={**os.environ, "GCM_INTERACTIVE": "never"},
        creationflags=PROCESS_FLAGS,
    )
    values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    token = values.get("password")
    if not token:
        raise RuntimeError("未找到 GitHub 凭据，无法自动更新 Pages 的 API 地址。")
    return token


def github_request(token: str, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    request = Request(
        f"https://api.github.com/repos/{GITHUB_REPOSITORY}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "DiceBot",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method=method,
    )
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        return exc.code, {}


def publish_tunnel_url(url: str) -> None:
    token = git_credential()
    variable = "/actions/variables/TABLETOP_API_URL"
    status, _ = github_request(token, "GET", variable)
    if status == 200:
        status, _ = github_request(token, "PATCH", variable, {"name": "TABLETOP_API_URL", "value": url})
        expected = 204
    elif status == 404:
        status, _ = github_request(token, "POST", "/actions/variables", {"name": "TABLETOP_API_URL", "value": url})
        expected = 201
    else:
        raise RuntimeError(f"读取 GitHub 仓库变量失败：HTTP {status}")
    if status != expected:
        raise RuntimeError(f"更新 GitHub 仓库变量失败：HTTP {status}")
    status, _ = github_request(token, "POST", "/actions/workflows/pages.yml/dispatches", {"ref": "main"})
    if status != 204:
        raise RuntimeError(f"触发 Pages 发布失败：HTTP {status}")
    print("已更新 GitHub Pages 的实时服务地址，并触发发布。", flush=True)


def port_in_use(port: int) -> bool:
    with socket.socket() as connection:
        connection.settimeout(0.4)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def wait_for_api(process: subprocess.Popen) -> None:
    for _ in range(50):
        if process.poll() is not None:
            raise RuntimeError("实时服务启动失败，请查看 data/quick-api.log。")
        try:
            with urlopen("http://127.0.0.1:8765/api/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            time.sleep(0.2)
    raise RuntimeError("实时服务未在 8765 端口就绪。")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-publish", action="store_true", help="只启动临时隧道，不更新 GitHub Pages")
    args = parser.parse_args()
    settings = dotenv_values(ROOT / ".env")
    if not settings.get("TABLETOP_ADMIN_TOKEN"):
        raise SystemExit("请先在 .env 设置 TABLETOP_ADMIN_TOKEN。")
    if port_in_use(8765) or port_in_use(8080):
        raise SystemExit("8765 或 8080 端口已在使用。请先停止旧的 Bot/实时服务。")
    environment = {**os.environ, **{key: value for key, value in settings.items() if value is not None}}
    data_dir = (ROOT / settings.get("TABLETOP_DATA_DIR", "data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    children: list[subprocess.Popen] = []
    try:
        with (data_dir / "quick-api.log").open("a", encoding="utf-8") as api_log, (data_dir / "quick-bot.log").open("a", encoding="utf-8") as bot_log:
            api = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "tabletop_server.app:app", "--host", "127.0.0.1", "--port", "8765"],
                cwd=ROOT, env=environment, stdout=api_log, stderr=subprocess.STDOUT,
                creationflags=PROCESS_FLAGS,
            )
            children.append(api)
            wait_for_api(api)
            bot = subprocess.Popen(
                [sys.executable, "bot.py"], cwd=ROOT, env=environment,
                stdout=bot_log, stderr=subprocess.STDOUT, creationflags=PROCESS_FLAGS,
            )
            children.append(bot)
            tunnel = subprocess.Popen(
                ["cloudflared", "tunnel", "--url", "http://127.0.0.1:8765", "--no-autoupdate"],
                cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", creationflags=PROCESS_FLAGS,
            )
            children.append(tunnel)
            print("实时服务与 QQ Bot 已启动，等待 Cloudflare 临时地址…", flush=True)
            published = False
            assert tunnel.stdout is not None
            for line in tunnel.stdout:
                found = TUNNEL_URL.search(line)
                if found and not published:
                    url = found.group(0)
                    print(f"临时实时服务：{url}", flush=True)
                    if not args.no_publish:
                        publish_tunnel_url(url)
                    published = True
                if bot.poll() is not None:
                    raise RuntimeError("QQ Bot 已退出，请查看 data/quick-bot.log。")
                if api.poll() is not None:
                    raise RuntimeError("实时服务已退出，请查看 data/quick-api.log。")
            raise RuntimeError("Cloudflare 隧道已结束。")
    except KeyboardInterrupt:
        print("正在停止临时隧道、实时服务与 QQ Bot…", flush=True)
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
        for child in reversed(children):
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()


if __name__ == "__main__":
    main()
