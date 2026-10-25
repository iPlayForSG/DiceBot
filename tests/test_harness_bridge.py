import time

import pytest

from harness_bridge.client import HarnessClient, HarnessError, session_key, validate_proxy_route


def test_harness_only_accepts_the_local_proxy():
    validate_proxy_route({'base_url':'http://127.0.0.1:8788/v1'})
    for address in ('https://api.deepseek.com/v1','https://api.deepseek.com/anthropic',
                    'http://127.0.0.1:8080/v1','http://example.com:8788/v1',
                    'http://key@127.0.0.1:8788/v1','http://127.0.0.1:8788/v1?redirect=official'):
        with pytest.raises(HarnessError):
            validate_proxy_route({'base_url':address})


def test_sessions_are_separate_for_groups_and_members():
    assert session_key('group-a','member-a') != session_key('group-a','member-b')
    assert session_key('group-a','member-a') != session_key('group-b','member-a')
    assert session_key('group-a','member-a') == session_key('group-a','member-a')
    assert '/' not in session_key('../../','../')


def test_incomplete_harness_turn_cannot_be_reported_as_success(tmp_path):
    client=HarnessClient(tmp_path,tmp_path,{'api_key':'test'})
    client.notifications=[{'method':'session.event','params':{'event':{
        'type':'assistant/message','data':{'content':[{'type':'text','text':'unfinished'}]}}}}]
    with pytest.raises(HarnessError):
        client._result(time.monotonic())


def test_profile_disables_official_routes_and_host_command_tools():
    from harness_bridge.client import ROOT
    import yaml
    # 去除只属于运行期的 JS 取值，检查静态的路由和能力边界。
    class ProfileLoader(yaml.SafeLoader):pass
    ProfileLoader.add_constructor('tag:yaml.org,2002:js',lambda loader,node:loader.construct_scalar(node))
    profile=yaml.load((ROOT/'harness_bridge/profile.patch.yml').read_text(encoding='utf-8'),Loader=ProfileLoader)
    disabled={row['id'] for row in profile if row.get('disabled') is True}
    assert {'llm-deepseek','session-log-deepseek','persistent-bash','persistent-pwsh','tool-fs','tool-working-directory'} <= disabled
    provider=next(row['insert'][0] for row in profile if 'insert' in row)
    route=provider['config']['providers']['dicebot-proxy']
    assert route['api']=='openai-completions'
    assert route['apiKeyEnv']=='DICEBOT_HARNESS_API_KEY'
