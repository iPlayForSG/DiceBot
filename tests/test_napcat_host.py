import json
from pathlib import Path

import pytest

from scripts.launch_napcat_portable import select_qq,refresh_package


def test_explicit_installed_qq_does_not_use_old_portable_copy(tmp_path):
    runtime=tmp_path/'runtime';runtime.mkdir()
    (runtime/'QQ.exe').write_bytes(b'old')
    installed=tmp_path/'installed';installed.mkdir()
    executable=installed/'QQ.exe';executable.write_bytes(b'new')
    assert select_qq(runtime,executable)==executable.resolve()


def test_saved_host_path_and_tim_rejection(tmp_path):
    executable=tmp_path/'QQ.exe';executable.write_bytes(b'qq')
    (tmp_path/'host.json').write_text(json.dumps({'qq_executable':str(executable)}),encoding='utf-8')
    assert select_qq(tmp_path)==executable.resolve()
    tim=tmp_path/'TIM.exe';tim.write_bytes(b'tim')
    with pytest.raises(ValueError):select_qq(tmp_path,tim)


def test_qq_vendor_version_is_preserved_in_runtime_patch(tmp_path):
    runtime=tmp_path/'runtime';runtime.mkdir()
    installation=tmp_path/'installed';version=installation/'versions/9.9.36-53644'
    (version/'resources/app').mkdir(parents=True)
    executable=installation/'QQ.exe';executable.write_bytes(b'qq')
    (installation/'versions/config.json').write_text(json.dumps({'curVersion':'9.9.36-53644'}),encoding='utf-8')
    (version/'resources/app/package.json').write_text(json.dumps({'productName':'QQ','version':'9.9.36-53644','main':'vendor.asar'}),encoding='utf-8')
    refresh_package(runtime,executable)
    patch=json.loads((runtime/'qqnt.json').read_text(encoding='utf-8'))
    assert patch['version']=='9.9.36-53644'
    assert patch['main']=='./loadNapCat.js'
    assert json.loads((version/'resources/app/package.json').read_text())['main']=='vendor.asar'
