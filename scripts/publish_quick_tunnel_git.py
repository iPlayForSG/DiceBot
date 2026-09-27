"""Publish a new Quick Tunnel URL with a repository-scoped GitHub deploy key."""

from pathlib import Path
import os
import re
import subprocess


REPOSITORY = "git@github.com:iPlayForSG/DiceBot.git"
QUICK_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com\Z")


def _run(args: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"Git command failed ({args[1]}): {result.stderr.strip()[-500:]}")
    return result.stdout.strip()


def publish(url: str, checkout: Path, private_key: Path) -> None:
    if not QUICK_URL.fullmatch(url):
        raise ValueError("Expected a Cloudflare Quick Tunnel HTTPS URL")
    private_key = private_key.resolve()
    if not private_key.is_file():
        raise FileNotFoundError(private_key)
    checkout = checkout.resolve()
    checkout.parent.mkdir(parents=True, exist_ok=True)
    environment = {
        **os.environ,
        "GIT_SSH_COMMAND": f'ssh -i "{private_key}" -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes',
        "GIT_TERMINAL_PROMPT": "0",
    }
    if not (checkout / ".git").is_dir():
        _run(["git", "clone", REPOSITORY, str(checkout)], cwd=checkout.parent, env=environment)
    if _run(["git", "status", "--porcelain"], cwd=checkout, env=environment):
        raise RuntimeError("Publisher checkout has local changes; preserving them for review")
    _run(["git", "pull", "--ff-only", "origin", "main"], cwd=checkout, env=environment)
    target = checkout / "deployment" / "api-url.txt"
    if target.read_text(encoding="utf-8").strip() == url:
        print("GitHub Pages already uses this tunnel URL.")
        return
    target.write_text(url + "\n", encoding="utf-8")
    _run(["git", "add", "deployment/api-url.txt"], cwd=checkout, env=environment)
    _run([
        "git", "-c", "user.name=DiceBot Tunnel",
        "-c", "user.email=dicebot-tunnel@users.noreply.github.com",
        "commit", "-m", "chore: update tabletop tunnel URL",
    ], cwd=checkout, env=environment)
    _run(["git", "push", "origin", "main"], cwd=checkout, env=environment)
    print("Published new tunnel URL to GitHub Pages source.")
