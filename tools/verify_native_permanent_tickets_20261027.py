MANIFEST_SHA='472184f163a953452076cb5e3bf0ca4dad0e9427c7696ea12b4dfa549ca3b732'
"""Verify exact ticket source archive and optional complete Clock parent."""
from pathlib import Path
import argparse,ast,json,hashlib,sqlite3
ROOT=Path(__file__).resolve().parents[1];ARCHIVE=ROOT/'references/native-two-permanent-tickets-20261027-v1'
digest=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--channel',choices=('online','local'),default='online');ap.add_argument('--artifact',type=Path);ap.add_argument('--parent',type=Path);ap.add_argument('--full-parent',action='store_true');a=ap.parse_args()
 assert digest(ARCHIVE/'manifest.json')==MANIFEST_SHA
 m=json.loads((ARCHIVE/'manifest.json').read_bytes());c=m['channels'][a.channel];rows=c['runtime_leaves'];assert len(rows)==10 and sum(r['new_file']for r in rows)==3
 paths={}
 for r in rows:
  p=a.artifact/r['path']if a.artifact else ARCHIVE/r['archive_path'];assert digest(p)==r['sha256']and p.stat().st_size==r['size'];paths[r['path']]=p
  if p.suffix=='.py':ast.parse(p.read_text('utf8'))
  elif p.suffix=='.json':json.loads(p.read_bytes())
 economy=json.loads(paths['els_server/data/formal_pve_economy.json'].read_bytes())
 for mid,item,solo in ((35080,118341,True),(35090,118341,True),(35340,118651,False),(35350,118651,False)):
  r=economy['maps'][str(mid)];assert item in r['current_display_pool']['COMMON']and r['additional_clear_drop']is solo and r['additional_group_clear_drop']is True
 storage=ast.parse(paths['els_server/storage/native_dungeon_tickets.py'].read_text('utf8'));ddl=[n.value for n in ast.walk(storage)if isinstance(n,ast.Constant)and isinstance(n.value,str)and n.value.startswith('CREATE TABLE IF NOT EXISTS native_dungeon_ticket')]
 assert len(ddl)==2
 with sqlite3.connect(':memory:')as db:
  for sql in ddl:db.execute(sql)
  assert db.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()==(2,)
 if a.parent:
  p=a.parent/c['parent_manifest_name'];assert digest(p)==c['parent_manifest_sha256'];parent={r['path']:r for r in json.loads(p.read_bytes())['files']}
  for r in rows:
   if r['new_file']:assert r['path']not in parent and not(a.parent/r['path']).exists()
   else:assert parent[r['path']]['sha256']==r['parent_sha256']and digest(a.parent/r['path'])==r['parent_sha256']
  for rel,h in c['preserved_parent_rows'].items():assert parent[rel]['sha256']==h and digest(a.parent/rel)==h
  if a.full_parent:
   for r in parent.values():assert digest(a.parent/r['path'])==r['sha256']
 print(json.dumps(dict(ok=True,channel=a.channel,delta10=True,new_files3=True,lazy_tables2=True,installDDL0=True,group_only_source_preserved=True,full_parent=bool(a.parent and a.full_parent))))
if __name__=='__main__':main()
