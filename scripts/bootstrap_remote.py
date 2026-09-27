"""Create a private .env for the Windows game host without printing secrets."""

from pathlib import Path
from secrets import token_urlsafe


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / ".env"


def main() -> None:
    if TARGET.exists():
        print("Existing .env preserved.")
        return

    replacements = {
        "ONEBOT_ACCESS_TOKEN": token_urlsafe(24),
        "TABLETOP_ADMIN_TOKEN": token_urlsafe(32),
        "TABLETOP_API_URL": "http://127.0.0.1:8765",
        "TABLETOP_PUBLIC_URL": "https://iplayforsg.github.io/DiceBot",
        "TABLETOP_ALLOWED_ORIGINS": "https://iplayforsg.github.io",
        "TABLETOP_DATA_DIR": "data",
    }
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    configured = []
    for line in lines:
        key = line.split("=", 1)[0]
        configured.append(f"{key}={replacements[key]}" if key in replacements else line)
    TARGET.write_text("\n".join(configured) + "\n", encoding="utf-8")
    print("Created .env with private Bot and API tokens (values hidden).")


if __name__ == "__main__":
    main()
