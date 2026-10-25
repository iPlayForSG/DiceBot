"""Create local-only control console settings and its isolated AstrBot config."""
import json
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bot_console.app import password_hash

state = ROOT / '.local-tools/bot-console'
state.mkdir(parents=True, exist_ok=True)
credentials_file = state / 'credentials.json'
if not credentials_file.exists():
    credentials_file.write_text(json.dumps({'console_password':secrets.token_urlsafe(18),
        'astrbot_password':'Aa1-' + secrets.token_urlsafe(18),
        'proxy_config':'D:/AI/workbuddy2api-hub/local-connection.json'}, indent=2), encoding='utf-8')
values = json.loads(credentials_file.read_text(encoding='utf-8'))
settings = {'password':password_hash(values['console_password']), 'cloud_host':'45.192.248.100',
    'cloud_key':str(ROOT / '.local-tools/cloud-deploy/id_ed25519'),
    'cloud_known_hosts':str(ROOT / '.local-tools/cloud-deploy/known_hosts'),
    'proxy_config':values['proxy_config']}
(state / 'settings.json').write_text(json.dumps(settings, indent=2), encoding='utf-8')
subprocess.run([str(ROOT / '.local-tools/astrbot/venv/Scripts/python.exe'), str(ROOT / 'scripts/configure_astrbot.py')], check=True)
print('Local console settings prepared. Passwords stay in the ignored runtime directory.')
