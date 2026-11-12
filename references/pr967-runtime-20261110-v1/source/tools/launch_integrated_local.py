"""Compatibility name: resolve the local release, then use the shared startup."""
import subprocess,sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
def main():
    from tools.release_channels import local_release
    selected=local_release(BASE)
    if selected!=BASE:return subprocess.call([sys.executable,str(selected/'tools/launch_integrated_local.py'),*sys.argv[1:]],cwd=selected)
    from launch_client import main as shared_main
    return shared_main(['--mode','local',*sys.argv[1:]])
if __name__=='__main__':raise SystemExit(main())
