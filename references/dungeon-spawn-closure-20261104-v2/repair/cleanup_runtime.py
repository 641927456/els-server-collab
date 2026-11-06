"""Remove only this turn's closed, owned materialized source view."""
import hashlib,json,os,shutil,stat,sys
from pathlib import Path
sys.dont_write_bytecode=True;sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'tools/pylibs'))
import psutil
W=Path(__file__).resolve().parent;preparation=json.loads((W/'runtime-preparation.json').read_bytes());D=Path(preparation['runtime']).resolve();R=Path(preparation['parent']);M=json.loads((W/'candidate-manifest.json').read_bytes())
assert D==W.resolve()/'runtime'and preparation['owned']and D.is_dir()
needle=str(D).lower();occupied=[]
for process in psutil.process_iter(['pid','cmdline']):
 try:
  if any(needle in str(arg).lower()for arg in(process.info['cmdline']or[])):occupied.append(process.info['pid'])
 except(psutil.AccessDenied,psutil.NoSuchProcess):continue
assert not occupied,occupied
for base,dirs,files in os.walk(D,followlinks=False):
 for name in dirs+files:
  path=Path(base)/name
  assert path.resolve().is_relative_to(D)
  assert not path.is_symlink()and not(getattr(path.lstat(),'st_file_attributes',0)&stat.FILE_ATTRIBUTE_REPARSE_POINT),str(path)
shutil.rmtree(D)
assert not D.exists()
H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
rows=json.loads((R/'rollup-manifest.json').read_bytes())['files']
assert all(H(R/r['path'])==r['sha256']for r in rows)
out=dict(ok=True,removed_owned_runtime=str(D),runtime_absent=True,owned_TLS_database_removed=json.loads((W/'dependency-TLS-tests.json').read_bytes())['owned_database_removed'],no_referenced_processes=True,parent_release_files_unchanged=len(rows),no_player_database_opened=True)
(W/'cleanup.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8');print(json.dumps(out))
