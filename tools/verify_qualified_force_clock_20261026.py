MANIFEST_SHA='4046682b9804f4873cdb0cbc45d1bf3812ec96d7e088a4e6ab7e10ca19419c1a'
"""Verify the exact Clock runtime archive and optional actual formal parent."""
from pathlib import Path
import ast,argparse,json,hashlib
ROOT=Path(__file__).resolve().parents[1];ARCHIVE=ROOT/'references/qualified-force-clock-20261026-v1'
digest=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--channel',choices=('online','local'),default='online');ap.add_argument('--artifact',type=Path);ap.add_argument('--parent',type=Path);ap.add_argument('--full-parent',action='store_true');a=ap.parse_args()
 assert digest(ARCHIVE/'manifest.json')==MANIFEST_SHA
 m=json.loads((ARCHIVE/'manifest.json').read_bytes());c=m['channels'][a.channel];assert len(c['runtime_leaves'])==9
 for row in c['runtime_leaves']:
  p=a.artifact/row['path']if a.artifact else ARCHIVE/row['archive_path'];assert p.is_file()and digest(p)==row['sha256']and p.stat().st_size==row['size']
  if p.suffix=='.py':ast.parse(p.read_text('utf8'))
  elif p.suffix=='.json':json.loads(p.read_bytes())
 inventory=next(r for r in c['runtime_leaves']if r['path'].endswith('/boosting2026-force-inventory.json'))
 p=a.artifact/inventory['path']if a.artifact else ARCHIVE/inventory['archive_path'];catalog=json.loads(p.read_bytes());books=catalog['reward_books']+catalog['upgrade_books']
 assert len(books)==21 and len({r['item']for r in books})==21
 clock=next(r for r in books if r['item']==295750);assert clock['skill']==900305 and clock['native_rank']==clock['native_grade']==6 and clock['active']and clock['permanent_only']and not clock.get('required_master',False)
 if a.parent:
  p=a.parent/c['parent_manifest_name'];assert digest(p)==c['parent_manifest_sha256'];rows={r['path']:r for r in json.loads(p.read_bytes())['files']}
  for row in c['runtime_leaves']:assert rows[row['path']]['sha256']==row['parent_sha256']and digest(a.parent/row['path'])==row['parent_sha256']
  for name in ('preserved_next8_source13','preserved_Board25','preserved_character3','preserved_roster1'):
   for rel,h in c[name].items():assert rows[rel]['sha256']==h and digest(a.parent/rel)==h
  if a.full_parent:
   for row in rows.values():assert digest(a.parent/row['path'])==row['sha256']
 print(json.dumps(dict(ok=True,channel=a.channel,source_files=9,Clock_rank6=True,owned_catalog21=True,full_parent=bool(a.parent and a.full_parent))))
if __name__=='__main__':main()
