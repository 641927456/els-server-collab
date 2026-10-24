"""Open existing offline GM tools with game launch delegated to the shared shell."""
import argparse,os,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);p.add_argument('--view',choices=('gm','backups'),default='gm');a=p.parse_args()
os.environ['ELS_LOCAL_USER_ROOT']=str(a.workspace.resolve())
os.environ['ELS_LOCAL_MANAGER_VIEW']=a.view
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.argv=[sys.argv[0]]
from launcher.__main__ import main
raise SystemExit(main())
