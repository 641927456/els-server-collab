"""Portable source/package validator. No server/client imports or mutations."""
import argparse,hashlib,json,re
from pathlib import Path
MANIFEST_SHA='71ba3be467dbfc79557a5e2b9633fc26628eaf7e2fee256f371c61d3071a28af'
ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/'references/qualified-force-next8-20261026-v1'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ARCHIVE/'shared');p.add_argument('--channel',choices=('online','local'),default='online');p.add_argument('--manifest',type=Path,default=ARCHIVE/'manifest.json');p.add_argument('--parent',type=Path);p.add_argument('--full-parent',action='store_true');a=p.parse_args()
 assert digest(a.manifest)==MANIFEST_SHA,'Manifest identity';m=json.loads(a.manifest.read_bytes());c=m['channels'][a.channel];root=a.root.resolve();rows=c['runtime_leaves'];assert len(rows)==13 and len({r['path']for r in rows})==13
 assert 'els_server/domain/formal_pve_economy.py'not in {r['path']for r in rows}
 for r in rows:
  rel=Path(r['path']);assert not rel.is_absolute()and '..'not in rel.parts;alternate=ARCHIVE/a.channel/rel;f=alternate if root==(ARCHIVE/'shared').resolve()and alternate.is_file()else root/rel;assert digest(f)==r['sha256'],r['path'];raw=f.read_bytes();assert len(raw)==r['size']
  assert not re.search(rb'(?i)[a-z]:[\\/]|Users[\\/]|BEGIN [A-Z ]*PRIVATE KEY',raw),r['path']
  if f.suffix=='.py':compile(raw,str(f),'exec')
  elif f.suffix=='.json':json.loads(raw)
 registry=root/'els_server/data/boosting2026-force-inventory.json';assert digest(registry)==m['registry_payload_sha256'];d=json.loads(registry.read_bytes());books={r['item']:r for key in('reward_books','upgrade_books')for r in d[key]};assert len(books)==20
 for key,sha in m['old_twelve_row_fingerprints'].items():assert hashlib.sha256(json.dumps(books[int(key)],sort_keys=True,separators=(',',':')).encode()).hexdigest()==sha
 assert {r['skill']for r in books.values()if r.get('active')}==set(m['required_ordinary_active_skills'])
 for t in m['qualified_owned_books']:
  ordinal={295762:6,311512:3,311518:3,311524:3,311527:3,311066:1,311515:1,311521:1}[t]
  r=books[t];assert r['required_stage']==3 and r['source_list_index']==ordinal and r['native_rank']==(6 if t==295762 else 5)and r['native_grade']==(6 if t==295762 else 1)
  assert bool(r.get('required_master'))==(t!=295762)and r['owned_only']is(t==295762)
  assert r.get('qualified_clear_sources',[])==[int(mid)for mid,v in m['qualified_source_maps'].items()if v==t]
 py=(root/'els_server/domain/boosting_2026_force_inventory.py').read_text('utf8');assert re.search(r"REGISTRY_SHA='([a-f0-9]{64})'",py).group(1)==digest(registry)
 economy=root/'els_server/data/formal_pve_economy.json';e=json.loads(economy.read_bytes());em=json.loads(economy.with_suffix('.manifest.json').read_bytes());assert em['payload_sha256']==digest(economy)
 assert e['local']['current_boss_display_completion_bp']==1000 and e['local']['quantity']==1
 for mid,t in m['qualified_source_maps'].items():
  r=e['maps'][mid];assert t in r['current_display_pool']['COMMON']and str(t)not in r['held_display_items']and str(t)not in e['held_display_items'];assert r['additional_clear_drop']and r['additional_group_clear_drop']and not r['existing_source_preserved']
 for t in m['hold_source_items']:assert str(t)in e['held_display_items']
 for mid in ('140010','140020','140030'):assert not any(295762 in pool for pool in e['maps'][mid]['current_display_pool'].values())
 assert all(295750 not in pool for pool in e['maps']['34060']['current_display_pool'].values())
 parent_files=0
 if a.parent:
  for r in rows:assert digest(a.parent/r['path'])==r['parent_sha256'],('parent leaf',r['path'])
  for r in c['preserved_character3']+c['preserved_Board25']:assert digest(a.parent/r['path'])==r['sha256'],('preserved parent',r['path'])
  assert digest(a.parent/'els_server/storage/boosting_2026_force_extraction.py')==c['legacy6CE_sha256']
  mf=a.parent/c['parent_manifest_name'];assert digest(mf)==c['parent_manifest_sha256']
  if a.full_parent:
   entries=json.loads(mf.read_bytes())['files'];assert len(entries)==c['parent_business_files']
   for r in entries:assert digest(a.parent/r['path'])==r['sha256'],('full parent',r['path'])
   parent_files=len(entries)
 elif a.full_parent:raise AssertionError('--full-parent needs --parent')
 print(json.dumps(dict(ok=True,channel=a.channel,runtime_leaves=13,catalog_rows=20,source_maps=8,source_books=7,parent_files_verified=parent_files,server_or_client_execution=False)))
if __name__=='__main__':main()
