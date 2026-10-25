"""Standalone Windows entry point for the local control console."""
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
state = ROOT / '.local-tools/bot-console'
state.mkdir(parents=True, exist_ok=True)
log = (state / 'managed.log').open('a', encoding='utf-8', buffering=1)
sys.stdout = log
sys.stderr = log
runpy.run_module('bot_console', run_name='__main__')
