"""Validate the exact shared Force source archive; never open an App or database."""
from pathlib import Path,PurePosixPath
import ast,hashlib,json,re
ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/'references/ordinary-active-force-books-20261026-v1'
EXPECTED={'els_server/data/boosting2026-force-inventory.json': 'af5018c577092c376707aa9ae07fa05f71d0496547125f9400604e9b45b75b46', 'els_server/data/formal_pve_economy.json': 'ecc9a17a81efc08da323e0b779c96e921c68dd789dc517f9b03dfd0afc15b170', 'els_server/data/formal_pve_economy.manifest.json': '4927c41672120265ba8fc1f62b7bed6f9eb9306ea4a5fd631c0f73b957ef285f', 'els_server/domain/boosting_2026_force_equipment.py': '1229e8e03a646fcb175cd3a853d68520528cbf06ef5d08a5def96c35d19b2b72', 'els_server/domain/boosting_2026_force_inventory.py': '51a86f0a0d681e9e24e87085d41f0fba2f7cb03edf043f3a04e75ed6d5b616df', 'els_server/domain/ordinary_skill_pages.py': '09469f7f627af7711b697d645ebfa1a0358154b6f480eea618202b17b9c455a9', 'els_server/domain/role_progression.py': '058093232a8827008cf295b2ce94ef84daf7101cc67007ad8d6c2ea1d7d58c6f', 'els_server/domain/skill_rules.py': 'a8b70d4b3c4ecddf9d7adc6421af06e36f13b6a519259cc82837b36572c7c266', 'els_server/storage/boosting_2026_force_equipment.py': 'bed0f81633010e87bd51f6baa5e57ef10a98289d3ffad26eb29ce7eef895b79c', 'els_server/storage/boosting_2026_force_extraction.py': 'd2a1d279d05c1a7747157eb0dca2b945e7307507151f757d1e6f16646fe6b3d6', 'els_server/storage/boosting_2026_force_inventory.py': '779ea9d6b1c8859fadbadaafdd37e1a65bc45b6121436f67632bcebaabd97aab', 'els_server/storage/force_rank4_schema.py': '168a17f53321cca8e7154b5870bd511c95f479803238bdeeef10f9c9a4a12464', 'els_server/storage/local_state.py': '947660698bee5891b8113d35b6bcb97a61ef18a85561883d975d48ed26f963fc', 'els_server/storage/ordinary_skill_pages.py': 'ae88f3b1e5e17218ea7ffb376a31ff8a9913412f20f5e7ab81afadc1fa64de1d'}
PAIRS={34000:295744,34010:295729,34030:295739}
ACTIVE={295729:900214,295739:900234,295744:900244}
OLD={295707,295708,295709,295712,295713,295714,306002,306003,306004}
def digest(raw):return hashlib.sha256(raw).hexdigest()
def canon(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def parse(rel):return json.loads((ARCHIVE/'shared'/rel).read_bytes())
def projection(d):
 d=json.loads(json.dumps(d))
 for mid,t in PAIRS.items():
  for p,k in((d['items'],str(t)),(d['held_display_items'],str(t)),(d['maps'][str(mid)]['held_display_items'],str(t)),(d['maps'][str(mid)]['current_display_pool'],'COMMON')):p.pop(k,None)
 return digest(canon(d))
def verify():
 m=json.loads((ARCHIVE/'manifest.json').read_bytes())
 assert m['schema_version']==1 and m['channel']=='shared'and m['verified_runtime_modes']==['online','local']
 assert m['unit_ids']==['ordinary-active-force-books']and m['physical_files']==14
 assert m['new_schema']is True and m['new_tables']==m['install_DDL_statements']==m['client_delta']==0 and m['lazy_business_DDL']is True
 assert not m['runtime_byte_mapping']and not m['private_configuration_or_player_data_included']and m['new_paths']==[]
 assert m['qualification']['owned_rank']==5 and m['qualification']['normal_hotbar_level']==1
 assert m['local_rule']['chance_percent']==10 and m['local_rule']['existing_probability_unchanged']
 assert {r['path']:r['sha256']for r in m['source_delta']}==EXPECTED
 seen=set()
 for row in m['source_delta']:
  rel=PurePosixPath(row['path']);loc=PurePosixPath(row['archive'])
  assert not rel.is_absolute()and '..'not in rel.parts and ':'not in str(rel)and '\\'not in str(rel)
  assert str(loc)=='shared/'+str(rel)
  p=ARCHIVE/loc;assert p.resolve().is_relative_to(ARCHIVE.resolve())and not p.is_symlink()
  raw=p.read_bytes();assert digest(raw)==row['sha256']and len(raw)==row['size']and len(row['parent_sha256'])==64
  text=raw.decode('utf8');assert not re.search(r'(?i)[a-z]:[\\/]|/(?:home|Users)/',text)
  if rel.suffix=='.py':compile(raw,str(loc),'exec')
  else:json.loads(raw)
  seen.add(str(loc))
 assert {p.relative_to(ARCHIVE).as_posix()for p in ARCHIVE.rglob('*')if p.is_file()}==seen|{'manifest.json'}
 reg=parse('els_server/data/boosting2026-force-inventory.json');items=reg['reward_books']+reg['upgrade_books'];assert {r['item']for r in items}==OLD|set(ACTIVE)
 assert digest(canon(sorted([r for r in items if r['item']in OLD],key=lambda r:r['item'])))==m['prior_nine_registry_rows_sha256']
 for r in items:
  if r['item']in ACTIVE:assert (r['skill'],r['native_rank'],r['source_list_index'],r['native_grade'],r['active'],r['permanent_only'])==(ACTIVE[r['item']],5,1,1,True,True)
 assert not PurePosixPath(reg['original_source']['path']).is_absolute()and ':'not in reg['original_source']['path']
 tree=ast.parse((ARCHIVE/'shared/els_server/domain/boosting_2026_force_inventory.py').read_text('utf8'))
 fixed=next(ast.literal_eval(n.value)for n in tree.body if isinstance(n,ast.Assign)and any(isinstance(x,ast.Name)and x.id=='REGISTRY_SHA'for x in n.targets))
 assert fixed==digest((ARCHIVE/'shared/els_server/data/boosting2026-force-inventory.json').read_bytes())
 cat=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='catalog');assert not any(isinstance(n,ast.Constant)and n.value=='original_source'for n in ast.walk(cat))
 e=parse('els_server/data/formal_pve_economy.json');assert projection(e)==m['unchanged_economy_projection_sha256']
 assert parse('els_server/data/formal_pve_economy.manifest.json')['payload_sha256']==digest((ARCHIVE/'shared/els_server/data/formal_pve_economy.json').read_bytes())
 for row in m['local_rule']['sources']:
  mid,t=row['map'],row['book'];assert PAIRS[mid]==t
  assert e['maps'][str(mid)]['current_display_pool']['COMMON']==row['parent_common']+[t]
  assert str(t)not in e['maps'][str(mid)]['held_display_items']and str(t)not in e['held_display_items']and str(t)in e['items']
 for mid in m['weapons_preserved']['maps']:assert e['maps'][mid]['early_weapon_appendix']
 for t in m['weapons_preserved']['items']:assert str(t)in e['items']and str(t)not in e['held_display_items']
 extraction=ast.parse((ARCHIVE/'shared/els_server/storage/boosting_2026_force_extraction.py').read_text('utf8'));action=next(n for n in extraction.body if isinstance(n,ast.FunctionDef)and n.name=='action')
 clock=next(n.lineno for n in ast.walk(action)if isinstance(n,ast.Assign)and any(isinstance(x,ast.Name)and x.id=='value'for x in n.targets))
 begin=next(n.lineno for n in ast.walk(action)if isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)and n.func.attr=='execute'and n.args and isinstance(n.args[0],ast.Constant)and n.args[0].value=='BEGIN IMMEDIATE')
 previous=next(n.lineno for n in ast.walk(action)if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='_previous');assert begin<clock<previous
 return dict(ok=True,channel='shared',exact_source_files=14,new_schema=True,new_tables=0,installDDL=0,old_nine_preserved=True,weapons_preserved=True,lock_then_clock=True,database_opened=False,runtime_or_combat_test=False)
if __name__=='__main__':print(json.dumps(verify()))
