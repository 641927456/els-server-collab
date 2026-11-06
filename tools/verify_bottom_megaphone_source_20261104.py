"""Verify the installed server announcement source archive without private assets."""
from pathlib import Path
import runpy
ROOT=Path(__file__).resolve().parents[1]
runpy.run_path(str(ROOT/'references/native-bottom-megaphone-20261104-v1/verify_contract.py'),run_name='__main__')
