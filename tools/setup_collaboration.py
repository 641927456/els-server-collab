"""Enable local commit checks without changing global Git settings."""
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parents[1]
subprocess.run(['git','config','--local','core.hooksPath','.githooks'],cwd=root,check=True)
print('Local commit guard enabled. Read CONTRIBUTING.md before your first change.')
