"""Exact accepted five-leaf descendant; inherited source/asset locators are immutable."""
from pathlib import Path
import copy,hashlib,json
PROFILE='channels/accessory-identification-accepted-20261031-v1.json'
PARENT='channels/owned-stones-nine-leaf-accepted-20261030-v1.json'
PARENT_SHA='76bed17ea60a8c8aeeaef387fd5590aec838adecd07b4124d53cbab7a80309b6'
REF='references/accessory-identification-20261030-v1'
PATHS={'els_server/data/accessory_identification_groups.json','els_server/domain/accessory_identification.py','els_server/domain/ordinary_accessories.py','els_server/storage/identification_ui.py','els_server/domain/character_custom.py'}
read=lambda p:json.loads(Path(p).read_bytes())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def validate(parent,profile,contract):
 assert profile['parent']==PARENT and profile['candidate']is False and profile['actual_dual_delivery_verified']is True
 assert profile['delta_business_files']==dict(online=5,local=5)and profile['new_files']==1 and profile['new_schema']is False and profile['new_hooks']==0
 assert set(contract['changed_paths'])==PATHS and {r['path']for r in contract['changes']}==PATHS
 delta={r['path']:r for r in contract['changes']}
 for mode,count in [('online',1317),('local',1342)]:
  before={r['path']:r for r in parent['channels'][mode]['files']};after={r['path']:r for r in profile['channels'][mode]['files']}
  assert len(after)==len(profile['channels'][mode]['files'])==count
  assert set(after)-set(before)=={'els_server/data/accessory_identification_groups.json'}and not set(before)-set(after)
  assert {n for n in after if after[n]!=before.get(n)}==PATHS
  for name,row in after.items():
   assert ('source'in row)!=('asset'in row)
   if name not in PATHS:assert row==before[name]
   else:
    assert row['sha256']==delta[name]['sha256']and row['size']==delta[name]['size']and row['source'].startswith(REF+'/source/'+row['sha256']+'/')
    assert(before.get(name)or{}).get('sha256')==delta[name]['parent_sha256']
  assert profile['channels'][mode]['release']==profile['accepted_heads'][mode]['release']
 return True
def verify(root):
 root=Path(root);assert sha(root/PARENT)==PARENT_SHA
 parent,profile,contract=read(root/PARENT),read(root/PROFILE),read(root/REF/'source-contract.json');validate(parent,profile,contract)
 assert read(root/'channels/current-engine.json')==dict(format=1,profile=PROFILE,accepted=profile['accepted_heads'])
 for mode in ('online','local'):
  for row in profile['channels'][mode]['files']:
   if row['path']in PATHS:assert sha(root/row['source'])==row['sha256']
 data=read(root/next(r['source']for r in profile['channels']['online']['files']if r['path']=='els_server/data/accessory_identification_groups.json'))
 assert len(data['templates'])==85 and set(data['pools'])=={'100920001','100920002','100920003','5143'}
 for key,pool in data['pools'].items():
  assert sum(r['weight']for r in pool['outcomes'])==10000
  if key!='5143':assert len(pool['outcomes'])==20 and {r['weight']for r in pool['outcomes']}=={500}and pool['reset']is False
  else:assert len(pool['outcomes'])==16 and pool['reset']is True
 receipt=read(root/REF/'accepted-delivery.json');assert receipt['ok']and receipt['heads']==profile['accepted_heads']and receipt['public_four_initial_identifications']and receipt['public_nirvana_reset_exactly_one_scroll']and receipt['public_customization634_635']and receipt['public_own_QA_cleaned']
 return dict(ok=True,changed_files=5,ordinary_accessory_templates=85,all_parent_locators_preserved=True,source_asset_kinds_preserved=True)
def verified_accessory_predecessor(profile,mode,entry,path,*,root):
 root=Path(root);verify(root);raw=read(root/PROFILE);resolved=copy.deepcopy(raw)
 for channel,head in raw['accepted_heads'].items():resolved['channels'][channel].update(head)
 assert profile==raw or profile==resolved,'Exact raw or resolved accessory profile required'
 parent=read(root/PARENT);before={r['path']:r for r in parent['channels'][mode]['files']}
 after={r['path']:r for r in profile['channels'][mode]['files']}
 assert entry==after[entry['path']]==before[entry['path']],'Changed accessory leaf cannot inherit historical proof'
 assert Path(path).resolve()==(root/entry['source']).resolve() and sha(path)==entry['sha256']
 from tools.verify_owned_stones_activation_20261030 import verified_nine_predecessor
 return verified_nine_predecessor(parent,mode,before[entry['path']],root/before[entry['path']]['source'],root=root)

if __name__=='__main__':print(json.dumps(verify(Path(__file__).resolve().parents[1])))
