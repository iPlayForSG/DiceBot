"""Start NapCat against a portable QQ directory without modifying installed QQ."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess


def select_qq(root: Path, explicit: Path | None = None) -> Path:
    settings = root / 'host.json'
    selected = explicit
    if selected is None and settings.exists():
        selected = Path(json.loads(settings.read_text(encoding='utf-8-sig'))['qq_executable'])
    selected = (selected or root / 'QQ.exe').resolve()
    if not selected.is_file() or selected.name.lower() != 'qq.exe':
        raise ValueError('A valid QQ.exe is required; TIM is not supported by this launcher')
    return selected


def refresh_package(root: Path, qq: Path):
    if qq.parent == root:
        return
    versions = qq.parent / 'versions/config.json'
    if not versions.is_file():
        raise ValueError('The selected QQNT installation has no version configuration')
    current = json.loads(versions.read_text(encoding='utf-8-sig'))['curVersion']
    package = qq.parent / 'versions' / current / 'resources/app/package.json'
    metadata = json.loads(package.read_text(encoding='utf-8-sig'))
    if metadata.get('productName') != 'QQ':
        raise ValueError('The selected host package is not Tencent QQ')
    # QQ 安装目录拥有版本信息，运行目录仅保存 NapCat 的入口补丁。
    metadata['main'] = './loadNapCat.js'
    (root / 'qqnt.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--qq", required=True)
    parser.add_argument("--qq-executable", type=Path)
    args = parser.parse_args()
    if not args.qq.isdecimal():
        raise SystemExit("QQ account must contain digits only")
    root = args.runtime.resolve()
    qq = select_qq(root,args.qq_executable)
    refresh_package(root,qq)
    required = ("NapCatWinBootMain.exe", "NapCatWinBootHook.dll", "qqnt.json", "napcat.mjs")
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
    log_dir=root/'logs'
    log_dir.mkdir(exist_ok=True)
    process=subprocess.Popen(
        [str(root / "NapCatWinBootMain.exe"), str(qq),
         str(root / "NapCatWinBootHook.dll"), args.qq],
        cwd=root, env=environment,
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    # 引导失败发生在 NapCat 日志初始化前；单独保留脱敏输出便于定位。
    with (log_dir/'launcher.log').open('a',encoding='utf-8',buffering=1) as output:
        for line in process.stdout:
            if '二维码解码URL' in line:
                line='二维码解码URL: [REDACTED]\n'
            line=re.sub(r'(?i)(token[\"\x27]?\s*[:=]\s*[\"\x27]?)[^\s\"\x27,<>]+',r'\1[REDACTED]',line)
            output.write(line)
    raise SystemExit(process.wait())


if __name__ == "__main__":
    main()
