"""Start NapCat against a portable QQ directory without modifying installed QQ."""

import argparse
import os
from pathlib import Path
import subprocess


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--qq", required=True)
    args = parser.parse_args()
    if not args.qq.isdecimal():
        raise SystemExit("QQ account must contain digits only")
    root = args.runtime.resolve()
    required = ("QQ.exe", "NapCatWinBootMain.exe", "NapCatWinBootHook.dll", "qqnt.json", "napcat.mjs")
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise SystemExit(f"NapCat runtime is incomplete: {', '.join(missing)}")
    if not (root / "config" / f"onebot11_{args.qq}.json").exists():
        raise SystemExit("Run bootstrap_napcat.py first")

    main_url = (root / "napcat.mjs").as_uri()
    (root / "loadNapCat.js").write_text(
        f'(async () => {{await import("{main_url}")}})()\n', encoding="utf-8"
    )
    environment = {
        **os.environ,
        "NAPCAT_PATCH_PACKAGE": str(root / "qqnt.json"),
        "NAPCAT_LOAD_PATH": str(root / "loadNapCat.js"),
        "NAPCAT_INJECT_PATH": str(root / "NapCatWinBootHook.dll"),
        "NAPCAT_LAUNCHER_PATH": str(root / "NapCatWinBootMain.exe"),
        "NAPCAT_MAIN_PATH": str(root / "napcat.mjs"),
    }
    raise SystemExit(subprocess.call(
        [str(root / "NapCatWinBootMain.exe"), str(root / "QQ.exe"),
         str(root / "NapCatWinBootHook.dll"), "-q", args.qq],
        cwd=root, env=environment,
    ))


if __name__ == "__main__":
    main()
