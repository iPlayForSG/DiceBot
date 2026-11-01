import os
from pathlib import Path
import runpy
import sys

ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0,str(ROOT))
log=(ROOT/'.local-tools/bot-console/cloud-link-startup.log').open('a',encoding='utf-8',buffering=1)
sys.stdout=log
sys.stderr=log
runpy.run_module('bot_console.cloud_link',run_name='__main__')
