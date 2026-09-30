"""Run the QQ bot, game API and a temporary Cloudflare tunnel together.

The tunnel URL changes on every restart. This script updates the Pages source
using a repository-scoped deploy key or a saved local GitHub credential.
Keep this terminal open while people play. Ctrl+C stops all child processes.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime
import json
import os
from pathlib import Path
from queue import Empty, Queue
import re
import socket
import subprocess
import sys
from threading import Thread
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
GITHUB_REPOSITORY = "iPlayForSG/DiceBot"
PROCESS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PUBLIC_HEALTH_INTERVAL_SECONDS = 45
PUBLIC_HEALTH_FAILURE_LIMIT = 3
TUNNEL_START_TIMEOUT_SECONDS = 90
PUBLISH_RETRY_SECONDS = 60


def record(message: str) -> None:
    path = ROOT / "data" / "quick-supervisor.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output:
        output.write(f"{datetime.now().isoformat(timespec='seconds')} {message}\n")
    try:
        print(message, flush=True)
    except (OSError, AttributeError, ValueError):
        pass


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


def publish_tunnel_url(url: str, settings: dict | None = None) -> None:
    if settings and settings.get("DICEBOT_GITHUB_DEPLOY_KEY"):
        from publish_quick_tunnel_git import publish

        checkout = Path(settings.get("DICEBOT_GITHUB_PUBLISHER", ROOT.parent / "DiceBotPublisher"))
        publish(url, checkout, Path(settings["DICEBOT_GITHUB_DEPLOY_KEY"]))
        return
    token = git_credential()
    path = "/contents/deployment/api-url.txt"
    status, current = github_request(token, "GET", path)
    if status not in (200, 404):
        raise RuntimeError(f"读取 GitHub Pages 地址文件失败：HTTP {status}")
    if status == 200:
        previous = base64.b64decode(current["content"]).decode("utf-8").strip()
        if previous == url:
            print("GitHub Pages already uses this tunnel URL.", flush=True)
            return
    body = {
        "message": "chore: update tabletop tunnel URL",
        "content": base64.b64encode((url + "\n").encode("utf-8")).decode("ascii"),
        "branch": "main",
    }
    if status == 200:
        body["sha"] = current["sha"]
    result, _ = github_request(token, "PUT", path, body)
    if result not in (200, 201):
        raise RuntimeError(f"更新 GitHub Pages 地址文件失败：HTTP {result}")
    print("已更新 GitHub Pages 地址文件并触发发布。", flush=True)


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


def public_health(url: str) -> bool:
    """Probe the actual public route, including Cloudflare TLS and the origin."""
    request = Request(f"{url}/api/health", headers={"User-Agent": "DiceBot-Supervisor"})
    try:
        with urlopen(request, timeout=8) as response:
            return response.status == 200 and json.load(response).get("status") == "ok"
    except (OSError, ValueError, TimeoutError):
        return False


def collect_tunnel_output(process: subprocess.Popen, lines: Queue) -> None:
    try:
        assert process.stdout is not None
        for line in process.stdout:
            lines.put((process, line))
    finally:
        lines.put((process, None))


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
            lines: Queue = Queue()
            tunnel: subprocess.Popen | None = None
            current_url = ""
            published = False
            started_at = 0.0
            next_health = 0.0
            next_publish = 0.0
            launch_at = time.monotonic()
            health_failures = 0
            restart_attempts = 0

            def start_tunnel() -> None:
                nonlocal tunnel, current_url, published, started_at, next_health, next_publish
                tunnel = subprocess.Popen(
                    [settings.get("TABLETOP_CLOUDFLARED_PATH") or "cloudflared", "tunnel",
                     "--url", "http://127.0.0.1:8765", "--no-autoupdate"],
                    cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", creationflags=PROCESS_FLAGS,
                )
                children.append(tunnel)
                Thread(target=collect_tunnel_output, args=(tunnel, lines), daemon=True).start()
                current_url = ""
                published = False
                started_at = time.monotonic()
                next_health = started_at + PUBLIC_HEALTH_INTERVAL_SECONDS
                next_publish = started_at
                record("等待 Cloudflare 临时地址…")

            def restart_tunnel(reason: str) -> None:
                nonlocal tunnel, current_url, published, launch_at, health_failures, restart_attempts
                record(reason)
                old = tunnel
                tunnel = None
                current_url = ""
                published = False
                health_failures = 0
                if old is not None and old.poll() is None:
                    old.terminate()
                    try:
                        old.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        old.kill()
                        old.wait(timeout=5)
                restart_attempts += 1
                delay = min(60, 5 * 2 ** min(restart_attempts - 1, 4))
                launch_at = time.monotonic() + delay

            record("实时服务与 QQ Bot 已启动，开始监测公网连接。")
            while True:
                if bot.poll() is not None:
                    raise RuntimeError("QQ Bot 已退出，请查看 data/quick-bot.log。")
                if api.poll() is not None:
                    raise RuntimeError("实时服务已退出，请查看 data/quick-api.log。")
                if tunnel is None and time.monotonic() >= launch_at:
                    start_tunnel()

                try:
                    process, line = lines.get(timeout=1)
                except Empty:
                    process, line = None, None
                if process is tunnel and line:
                    found = TUNNEL_URL.search(line)
                    if found and not current_url:
                        current_url = found.group(0)
                        (data_dir / "current-tunnel-url.txt").write_text(current_url + "\n", encoding="utf-8")
                        record(f"临时实时服务：{current_url}")
                        next_health = time.monotonic() + 15
                        next_publish = time.monotonic()

                now = time.monotonic()
                if tunnel is not None and tunnel.poll() is not None:
                    restart_tunnel("Cloudflare 进程已退出，准备重新建隧道。")
                    continue
                if tunnel is not None and not current_url and now - started_at > TUNNEL_START_TIMEOUT_SECONDS:
                    restart_tunnel("Cloudflare 在限时内未给出地址，准备重新建隧道。")
                    continue
                if current_url and not published and now >= next_publish:
                    if args.no_publish:
                        published = True
                    else:
                        try:
                            publish_tunnel_url(current_url, settings)
                            published = True
                            record("GitHub Pages 地址已更新。")
                        except Exception as exc:
                            record(f"发布隧道地址失败，稍后重试：{type(exc).__name__}: {exc}")
                            next_publish = time.monotonic() + PUBLISH_RETRY_SECONDS
                if current_url and now >= next_health:
                    if public_health(current_url):
                        if health_failures:
                            record("公网实时服务连接已恢复。")
                        health_failures = 0
                        restart_attempts = 0
                    else:
                        health_failures += 1
                        record(f"公网实时服务检查失败（连续 {health_failures} 次）。")
                        if health_failures >= PUBLIC_HEALTH_FAILURE_LIMIT:
                            restart_tunnel("公网地址已失效，准备重新建隧道并更新网站。")
                            continue
                    next_health = time.monotonic() + PUBLIC_HEALTH_INTERVAL_SECONDS
    except KeyboardInterrupt:
        record("正在停止临时隧道、实时服务与 QQ Bot…")
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
    try:
        main()
    except Exception as exc:
        record(f"ERROR {type(exc).__name__}: {exc}")
        raise
