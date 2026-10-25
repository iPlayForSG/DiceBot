"""Initialize the isolated AstrBot runtime without copying upstream credentials."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil

ROOT = Path(__file__).resolve().parents[1]
runtime = ROOT / '.local-tools/astrbot/runtime'
runtime.mkdir(parents=True, exist_ok=True)
os.environ['ASTRBOT_ROOT'] = str(runtime)
os.chdir(runtime)
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.utils.auth_password import hash_dashboard_password

credentials = json.loads((ROOT / '.local-tools/bot-console/credentials.json').read_text(encoding='utf-8'))
proxy = json.loads(Path(credentials['proxy_config']).read_text(encoding='utf-8-sig'))
path = runtime / 'data/cmd_config.json'
path.parent.mkdir(parents=True, exist_ok=True)
config = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else deepcopy(DEFAULT_CONFIG)
token_file = runtime / 'onebot-token.txt'
if not token_file.exists():
    token_file.write_text(secrets.token_urlsafe(36), encoding='utf-8')
config['platform'] = [{'id':'dicebot-ai', 'type':'aiocqhttp', 'enable':True,
    'ws_reverse_host':'127.0.0.1', 'ws_reverse_port':6199,
    'ws_reverse_token':token_file.read_text(encoding='utf-8')}]
config['provider_sources'] = []
config['provider'] = [{'id':'workbuddy-flash', 'provider':'openai', 'type':'openai_chat_completion',
    'provider_type':'chat_completion', 'enable':True, 'key':['$DICEBOT_PROXY_API_KEY'],
    'api_base':proxy['base_url'], 'model':proxy['model'], 'timeout':90,
    'custom_extra_body':{'max_tokens':768, 'reasoning_effort':'low'}}]
config['agent_runner']['config']['model'].update(provider_id='workbuddy-flash', request_max_retries=1)
config['agent_runner']['config']['misc']['max_steps'] = 3
config['agent_runner']['config']['compression']['max_turns'] = 12
config['wake_prefix'] = ['/ai']
config['admins_id'] = []
config['plugin_set'] = ['dicebot_isolation']
config['platform_settings'].update(unique_session=True, enable_id_white_list=False,
    friend_message_needs_wake_prefix=True, ignore_bot_self_message=True, ignore_at_all=True,
    disable_builtin_commands=True, no_permission_reply=False)
config['platform_settings']['rate_limit'].update(time=60, count=6, strategy='discard')
config['provider_settings'].update(streaming_response=False, web_search=False, computer_use_runtime='none')
config['provider_settings']['proactive_capability']['add_cron_tools'] = False
config['dashboard'].update(host='127.0.0.1', username='admin', port=6185,
    password=hashlib.md5(credentials['astrbot_password'].encode()).hexdigest(),
    pbkdf2_password=hash_dashboard_password(credentials['astrbot_password']),
    password_storage_upgraded=True, password_change_required=False)
path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
destination = runtime / 'data/plugins/dicebot_isolation'
shutil.copytree(ROOT / 'astrbot_extensions/dicebot_isolation', destination, dirs_exist_ok=True)
print('AstrBot configured with isolated data, prefix filtering and local proxy credentials.')
