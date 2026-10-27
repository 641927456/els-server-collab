MANIFEST_SHA='20c9d8b995608e4fe3f633f5e262668053b0ba48bc81721887ccc8e9cfe9c452'
from pathlib import Path
import argparse,ast,copy,hashlib,json
ROOT=Path(__file__).resolve().parents[1];ARCHIVE=ROOT/'references/native-rosso-reset-20261027-v1'
digest=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--channel',choices=('online','local'),default='online');ap.add_argument('--artifact',type=Path);ap.add_argument('--parent',type=Path);ap.add_argument('--full-parent',action='store_true');a=ap.parse_args()
 assert digest(ARCHIVE/'manifest.json')==MANIFEST_SHA
 m=json.loads((ARCHIVE/'manifest.json').read_bytes());c=m['channels'][a.channel];rows=c['runtime_leaves'];assert len(rows)==7 and sum(r['new_file']for r in rows)==2
 paths={}
 for r in rows:
  p=a.artifact/r['path']if a.artifact else ARCHIVE/r['archive_path'];assert digest(p)==r['sha256']and p.stat().st_size==r['size'];paths[r['path']]=p
  if p.suffix=='.py':ast.parse(p.read_text('utf8'))
  elif p.suffix=='.json':json.loads(p.read_bytes())
 economy=json.loads(paths['els_server/data/formal_pve_economy.json'].read_bytes());row=economy['maps']['34160'];assert row['current_display_pool']['COMMON'].count(135909)==1 and 135909 in economy['new_reader_ids']
 for rel in ('els_server/domain/rosso_reset.py','els_server/storage/rosso_reset.py'):
  tree=ast.parse(paths[rel].read_text('utf8'));assert not any(isinstance(n,ast.Constant)and isinstance(n.value,str)and 'CREATE TABLE'in n.value.upper()for n in ast.walk(tree))
 if a.parent:
  p=a.parent/c['parent_manifest_name'];assert digest(p)==c['parent_manifest_sha256'];parent={r['path']:r for r in json.loads(p.read_bytes())['files']}
  for r in rows:
   if r['new_file']:assert r['path']not in parent and not(a.parent/r['path']).exists()
   else:assert parent[r['path']]['sha256']==r['parent_sha256']and digest(a.parent/r['path'])==r['parent_sha256']
  for rel,h in c['preserved_parent_rows'].items():assert parent[rel]['sha256']==h and digest(a.parent/rel)==h
  original=json.loads((a.parent/'els_server/data/formal_pve_economy.json').read_bytes());inverse=copy.deepcopy(economy);inverse['new_reader_ids'].remove(135909);inverse['maps']['34160']['current_display_pool']['COMMON'].remove(135909);inverse['maps']['34160']['held_display_items']['135909']=original['maps']['34160']['held_display_items']['135909'];inverse['held_display_items']['135909']=original['held_display_items']['135909'];del inverse['items']['135909'];assert inverse==original
  if a.full_parent:
   for r in parent.values():assert digest(a.parent/r['path'])==r['sha256']
 print(json.dumps(dict(ok=True,channel=a.channel,delta7=True,new_files2=True,new_tables0=True,installDDL0=True,full_parent=bool(a.parent and a.full_parent))))
if __name__=='__main__':main()
