"""Verify the archived attendance reward repair source contract."""
from pathlib import Path
import runpy
root=Path(__file__).resolve().parents[1]
runpy.run_path(str(root/'references/attendance-reward-validation-20261104-v1/verify_contract.py'),run_name='__main__')
