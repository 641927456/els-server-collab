"""Verify the installed pillar support archive without private binaries."""
from pathlib import Path
import runpy
ROOT=Path(__file__).resolve().parents[1]
runpy.run_path(str(ROOT/'references/plegas-pillar-20261104-v1/verify_contract.py'),run_name='__main__')
