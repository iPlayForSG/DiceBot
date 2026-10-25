#!/bin/bash
set -euo pipefail
release="$1"
case "$release" in /opt/dicebot/releases/*) ;; *) echo 'Invalid release path' >&2; exit 1;; esac
python3 -m venv /opt/dicebot/venv
/opt/dicebot/venv/bin/pip --quiet install --require-hashes -r "$release/deployment/cloud-requirements.txt"
chmod -R a+rX "$release"
# 房间数据与密钥属于运行环境，发布代码不得覆盖它们。
ln -sfn "$release" /opt/dicebot/current
install -m 644 "$release"/deployment/linux/dicebot-*.service /etc/systemd/system/
install -m 644 "$release"/deployment/linux/dicebot-cert-renew.timer /etc/systemd/system/
install -m 644 "$release"/deployment/linux/nginx.conf /etc/nginx/sites-available/dicebot
nginx -t
systemctl daemon-reload
systemctl enable dicebot-api dicebot-bot dicebot-cert-renew.timer
systemctl restart dicebot-api dicebot-bot
systemctl start dicebot-cert-renew.timer
systemctl reload nginx
for attempt in $(seq 1 30); do
    if curl --silent --fail http://127.0.0.1:8765/api/health; then
        # 保留当前版本和一个回退版本，避免发布包耗尽小容量系统盘。
        python3 - "$release" <<'PY'
from pathlib import Path
import shutil
import sys
root = Path('/opt/dicebot/releases')
current = Path(sys.argv[1]).resolve()
releases = sorted((p for p in root.iterdir() if p.is_dir() and not p.is_symlink()), reverse=True)
keep = {current, *(p.resolve() for p in releases[:2])}
for path in releases:
    if path.resolve().parent != root or path.resolve() in keep:
        continue
    shutil.rmtree(path)
PY
        exit 0
    fi
    sleep 1
done
systemctl status dicebot-api --no-pager
exit 1
