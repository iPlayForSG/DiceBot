"""Create NapCat's private reverse-WebSocket config for this Bot."""

import argparse
import json
from pathlib import Path

from dotenv import dotenv_values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--qq", required=True)
    args = parser.parse_args()
    if not args.qq.isdecimal():
        raise SystemExit("QQ account must contain digits only")
    root = Path(__file__).resolve().parents[1]
    token = dotenv_values(root / ".env").get("ONEBOT_ACCESS_TOKEN")
    if not token:
        raise SystemExit("ONEBOT_ACCESS_TOKEN is missing from .env")

    directory = args.runtime.resolve() / "config"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"onebot11_{args.qq}.json"
    if target.exists():
        print("Existing NapCat OneBot config preserved.")
        return
    config = {
        "network": {
            "httpServers": [],
            "httpSseServers": [],
            "httpClients": [],
            "websocketServers": [],
            "websocketClients": [{
                "name": "DiceBot",
                "enable": True,
                "url": "ws://127.0.0.1:8080/onebot/v11/ws",
                "messagePostFormat": "array",
                "reportSelfMessage": False,
                "reconnectInterval": 5000,
                "token": token,
                "debug": False,
                "heartInterval": 30000,
            }],
            "plugins": [],
        },
        "musicSignUrl": "",
        "enableLocalFile2Url": False,
        "parseMultMsg": False,
        "imageDownloadProxy": "",
    }
    target.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print("NapCat reverse WebSocket configured with the private Bot token (hidden).")


if __name__ == "__main__":
    main()
