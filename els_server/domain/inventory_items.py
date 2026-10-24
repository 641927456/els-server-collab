"""Experimental native item records, initially the verified local potion reward."""
from els_server.paths import PROJECT_ROOT
import functools,hashlib,json,struct
from pathlib import Path
BASE=PROJECT_ROOT/'analysis/client-6c6b5180'
CLIENT_SHA='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
LOCAL_BAG_CAPACITY=36
LOCAL_MAX_STACK=999
VERIFIED_TEMPLATES={77000:2}  # Native name: 初级体力药水; metadata byte, not a grade.
TEMPLATE_BAG_GROUPS={77000:6}  # Enum.lua SORT_TYPE.ST_QUICK_SLOT; native flask tab.
TEMPLATE_MAX_STACKS={77000:99}
FASHION_POSITIONS={2:10,8:2,9:4,10:6,11:8,6:0,
                  48:43,49:44,50:45,51:46,52:47,53:48,54:49,55:50,56:51,57:52,58:53,59:54}
FASHION_EQUIP_SLOTS={}

def fashion_catalog():
 c=json.loads((BASE/'fashion-catalog.json').read_text(encoding='utf8'))
 if c['client_sha256']!=CLIENT_SHA:raise ValueError('Fashion catalog build mismatch')
 for path_key,hash_key in [('catalog_evidence','catalog_sha256'),('body_verification','body_verification_sha256')]:
  if hashlib.sha256((BASE/c[path_key]).read_bytes()).hexdigest()!=c[hash_key]:raise ValueError('Fashion catalog evidence changed')
 proof=json.loads((BASE/c['body_verification']).read_text(encoding='utf8'))
 if proof.get('ok')!=1 or proof.get('consumed')!=304 or not proof.get('fields_match') or proof.get('native_template_id')!=81021 or proof.get('applied_to_game') is not False:raise ValueError('Fashion native body proof mismatch')
 records={r['id']:bytes.fromhex(r['record_hex']) for r in json.loads((BASE/c['catalog_evidence']).read_text(encoding='utf8'))['rows']}
 for t in c['templates']:
  raw=records[t['template']];flags4,flags8=struct.unpack_from('<II',raw,4)
  native_group=27 if flags8&256 else 7
  if not flags4&1 or flags4&32 or t['group']!=native_group or hashlib.sha256(raw).hexdigest()!=t['resource_record_sha256']:raise ValueError('Fashion native classification mismatch')
 return c

for _fashion in fashion_catalog()['templates']:
 VERIFIED_TEMPLATES[_fashion['template']]=_fashion['metadata']
 TEMPLATE_BAG_GROUPS[_fashion['template']]=_fashion['group']
 TEMPLATE_MAX_STACKS[_fashion['template']]=_fashion['max_stack']
 FASHION_EQUIP_SLOTS[_fashion['template']]=FASHION_POSITIONS[_fashion['resource_position_byte']]

def ice_catalog():
 c=json.loads((BASE/'ice-catalog.json').read_text(encoding='utf8'))
 if c['client_sha256']!=CLIENT_SHA:raise ValueError('Ice item build mismatch')
 for path_key,hash_key in [('catalog_evidence','catalog_sha256'),('body_verification','body_sha256')]:
  if hashlib.sha256((BASE/c[path_key]).read_bytes()).hexdigest()!=c[hash_key]:raise ValueError('Ice item evidence changed')
 proof=json.loads((BASE/c['body_verification']).read_text(encoding='utf8'))
 if proof.get('ok')!=1 or proof.get('consumed')!=304 or not proof.get('fields_match') or proof.get('native_template_id')!=800000 or proof.get('applied_to_game') is not False:raise ValueError('Ice item native body mismatch')
 raw=bytes.fromhex(next(x for x in json.loads((BASE/c['catalog_evidence']).read_text(encoding='utf8'))['rows'] if x['id']==800000)['record_hex'])
 f4,f8=struct.unpack_from('<II',raw,4)
 if f4&33 or (f8>>3)&31!=7 or raw[7]&15!=c['metadata'] or c['group']!=4:raise ValueError('Ice item classification mismatch')
 return c

_ice=ice_catalog()
VERIFIED_TEMPLATES[_ice['template']]=_ice['metadata']
TEMPLATE_BAG_GROUPS[_ice['template']]=_ice['group']
TEMPLATE_MAX_STACKS[_ice['template']]=_ice['max_stack']

@functools.lru_cache(maxsize=1)
def native_ice_catalog():
 c=json.loads((BASE/'native-ice-shop-catalog.json').read_text(encoding='utf8'))
 if c['client_sha256']!=CLIENT_SHA:raise ValueError('Native ice catalog build mismatch')
 for s in c['sources']:
  if hashlib.sha256((BASE/s['path']).read_bytes()).hexdigest()!=s['sha256']:raise ValueError('Native ice source changed')
 proof=json.loads((BASE/'native-ice-shop-body-proof.json').read_text(encoding='utf8'))
 if proof['catalog_sha256']!=hashlib.sha256((BASE/'native-ice-shop-catalog.json').read_bytes()).hexdigest() or not proof['all_passed']:raise ValueError('Native ice body proof mismatch')
 return c

for _row in native_ice_catalog()['offers']+native_ice_catalog()['rewards']:
 _raw=bytes.fromhex(_row['record_hex'])
 if len(_raw)!=232 or struct.unpack_from('<I',_raw)[0]!=_row['template'] or _raw[7]&15!=_row['metadata']:raise ValueError('Native catalog record mismatch')
 VERIFIED_TEMPLATES[_row['template']]=_row['metadata']
 TEMPLATE_BAG_GROUPS[_row['template']]=_row['group']
 TEMPLATE_MAX_STACKS[_row['template']]=_row['max_stack']
 if _row['group']==27 and _row.get('resource_position_byte') in FASHION_POSITIONS:
  FASHION_EQUIP_SLOTS[_row['template']]=FASHION_POSITIONS[_row['resource_position_byte']]

@functools.lru_cache(maxsize=1)
def role_ice_catalog():
 path=BASE/'role-ice-catalog.json';c=json.loads(path.read_text(encoding='utf8'))
 if c['client_sha256']!=CLIENT_SHA:raise ValueError('Role ice build mismatch')
 for source in c['sources']:
  if hashlib.sha256((BASE/source['path']).read_bytes()).hexdigest()!=source['sha256']:raise ValueError('Role ice source changed')
 proof=json.loads((BASE/'role-ice-body-proof.json').read_text(encoding='utf8'))
 if proof['catalog_sha256']!=hashlib.sha256(path.read_bytes()).hexdigest() or not proof['all_passed'] or proof['count']!=len(proof['rows']) or proof['count']!=len(c['rewards']):raise ValueError('Role ice native proof mismatch')
 return c

for _row in role_ice_catalog()['rewards']:
 _raw=bytes.fromhex(_row['record_hex'])
 if len(_raw)!=232 or struct.unpack_from('<I',_raw)[0]!=_row['template'] or _raw[7]&15!=_row['metadata']:raise ValueError('Role ice record mismatch')
 VERIFIED_TEMPLATES[_row['template']]=_row['metadata']
 TEMPLATE_BAG_GROUPS[_row['template']]=_row['group']
 TEMPLATE_MAX_STACKS[_row['template']]=_row['max_stack']
 if _row['group']==27 and _row['resource_position_byte'] in FASHION_POSITIONS:
  FASHION_EQUIP_SLOTS[_row['template']]=FASHION_POSITIONS[_row['resource_position_byte']]

@functools.lru_cache(maxsize=1)
def extended_shop_catalog():
 path=BASE/'extended-shop-catalog.json';c=json.loads(path.read_text(encoding='utf8'))
 if c['client_sha256']!=CLIENT_SHA:raise ValueError('Extended shop build mismatch')
 for source in c['sources']:
  if hashlib.sha256((BASE/source['path']).read_bytes()).hexdigest()!=source['sha256']:raise ValueError('Extended shop source changed')
 proof=json.loads((BASE/'extended-shop-body-proof.json').read_text(encoding='utf8'))
 if proof.get('catalog_sha256')!=hashlib.sha256(path.read_bytes()).hexdigest() or proof.get('all_passed') is not True:raise ValueError('Extended shop native proof mismatch')
 evidence={p['template']:p for p in proof['rows']}
 if len(evidence)!=len(c['offers']) or proof.get('count')!=len(c['offers']):raise ValueError('Extended shop proof coverage')
 for row in c['offers']:
  raw=bytes.fromhex(row['record_hex']);p=evidence.get(row['template'],{})
  if len(raw)!=232 or struct.unpack_from('<I',raw)[0]!=row['template'] or raw[7]&15!=row['metadata']:raise ValueError('Extended shop record mismatch')
  if not (p.get('ok')==1 and p.get('consumed')==304 and p.get('fields_match') and p.get('vectors_empty') and p.get('native_template_id')==row['template'] and p.get('native_group')==row['group'] and p.get('applied_to_game') is False):raise ValueError('Extended shop item validation mismatch')
 return c

for _row in extended_shop_catalog()['offers']:
 if _row['template'] in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_row['template']],TEMPLATE_BAG_GROUPS[_row['template']])!=(_row['metadata'],_row['group']):raise ValueError('Conflicting extended item classification')
 VERIFIED_TEMPLATES[_row['template']]=_row['metadata']
 TEMPLATE_BAG_GROUPS[_row['template']]=_row['group']
 TEMPLATE_MAX_STACKS[_row['template']]=_row['max_stack']
 if _row['group'] in (7,27) and _row['resource_position_byte'] in FASHION_POSITIONS:
  FASHION_EQUIP_SLOTS[_row['template']]=FASHION_POSITIONS[_row['resource_position_byte']]

from els_server.domain.fashion_bundles import catalog as fashion_bundle_catalog
for _row in fashion_bundle_catalog()['definitions']:
 if _row['template'] in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_row['template']],TEMPLATE_BAG_GROUPS[_row['template']])!=(_row['metadata'],_row['group']):raise ValueError('Conflicting bundle item classification')
 VERIFIED_TEMPLATES[_row['template']]=_row['metadata']
 TEMPLATE_BAG_GROUPS[_row['template']]=_row['group']
 TEMPLATE_MAX_STACKS[_row['template']]=_row['max_stack']
 if _row['group'] in (7,27) and _row['resource_position_byte'] in FASHION_POSITIONS:
  FASHION_EQUIP_SLOTS[_row['template']]=FASHION_POSITIONS[_row['resource_position_byte']]

from els_server.domain.shop_additions import catalog as shop_additions_catalog
for _name in ('standalone','ice-common'):
 for _row in shop_additions_catalog(_name)['definitions']:
  if _row['template'] in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_row['template']],TEMPLATE_BAG_GROUPS[_row['template']],TEMPLATE_MAX_STACKS[_row['template']])!=(_row['metadata'],_row['group'],_row['max_stack']):raise ValueError('Conflicting supplement item definition')
  VERIFIED_TEMPLATES[_row['template']]=_row['metadata']
  TEMPLATE_BAG_GROUPS[_row['template']]=_row['group']
  TEMPLATE_MAX_STACKS[_row['template']]=_row['max_stack']
  if _row['group'] in (7,27) and _row['resource_position_byte'] in FASHION_POSITIONS:
   FASHION_EQUIP_SLOTS[_row['template']]=FASHION_POSITIONS[_row['resource_position_byte']]

def expansion_inventory_templates():
 """Only enable coupons with native private-body and classification evidence."""
 from els_server.game_data import client_data
 proof=json.loads((PROJECT_ROOT/'els_server/data/expansion_items.json').read_text(encoding='utf8'))
 if proof['client_sha256']!=CLIENT_SHA or proof['enabled_inventory_templates']!=[274160]:raise ValueError('Expansion item evidence scope')
 rows={r['template']:r for r in proof['rows']}
 result=[]
 for template in proof['enabled_inventory_templates']:
  item=client_data().item(template);p=rows[template]
  if hashlib.sha256(item['record']).hexdigest()!=proof['source_record_hashes'][str(template)] or item['item_type']!=7:raise ValueError('Expansion item resource mismatch')
  if not (p['ok']==1 and p['consumed']==304 and p['fields_match'] and p['vectors_empty'] and p['native_template_id']==template and p['native_group']==4 and p['private_data_item']['metadata']==item['metadata'] and p['applied_to_game'] is False):raise ValueError('Expansion item body proof mismatch')
  result.append((template,item['metadata']))
 return result

for _template,_metadata in expansion_inventory_templates():
 VERIFIED_TEMPLATES[_template]=_metadata
 TEMPLATE_BAG_GROUPS[_template]=4
 TEMPLATE_MAX_STACKS[_template]=99

from els_server.domain.equipment_attributes import inventory_definitions
for _row in inventory_definitions():
 if _row['template'] in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_row['template']],TEMPLATE_BAG_GROUPS[_row['template']],TEMPLATE_MAX_STACKS[_row['template']])!=(_row['metadata'],_row['group'],_row['max_stack']):raise ValueError('Conflicting attribute inventory template')
 VERIFIED_TEMPLATES[_row['template']]=_row['metadata']
 TEMPLATE_BAG_GROUPS[_row['template']]=_row['group']
 TEMPLATE_MAX_STACKS[_row['template']]=_row['max_stack']

from els_server.domain.normal_equipment import definitions as normal_equipment_definitions
for _template,_row in normal_equipment_definitions().items():
 if _template in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_template],TEMPLATE_BAG_GROUPS[_template],TEMPLATE_MAX_STACKS[_template])!=(_row['metadata'],_row['group'],_row['max_stack']):raise ValueError('Conflicting normal equipment definition')
 VERIFIED_TEMPLATES[_template]=_row['metadata']
 TEMPLATE_BAG_GROUPS[_template]=_row['group']
 TEMPLATE_MAX_STACKS[_template]=_row['max_stack']

from els_server.domain.role_progression import catalog as role_progression_catalog
for _row in role_progression_catalog()['costumes'].values():
 if _row['template'] in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_row['template']],TEMPLATE_BAG_GROUPS[_row['template']])!=(_row['metadata'],_row['group']):raise ValueError('Conflicting starter costume definition')
 VERIFIED_TEMPLATES[_row['template']]=_row['metadata']
 TEMPLATE_BAG_GROUPS[_row['template']]=_row['group']
 TEMPLATE_MAX_STACKS[_row['template']]=_row['max_stack']
 FASHION_EQUIP_SLOTS[_row['template']]=_row['equip_slot']

from els_server.domain.skill_unlocks import catalog as skill_unlock_catalog
for _row in skill_unlock_catalog()['books'].values():
 if _row['template'] in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_row['template']],TEMPLATE_BAG_GROUPS[_row['template']])!=(_row['metadata'],_row['group']):raise ValueError('Conflicting skill book classification')
 VERIFIED_TEMPLATES[_row['template']]=_row['metadata']
 TEMPLATE_BAG_GROUPS[_row['template']]=_row['group']
 TEMPLATE_MAX_STACKS[_row['template']]=_row['max_stack']

from els_server.domain.seal_quests import seal_catalog as seal_quest_catalog
from els_server.domain.region_quests import region_catalog as region_quest_catalog
from els_server.domain.story_quests import story_catalog as story_quest_catalog
from els_server.domain.job_quests import catalog as job_quest_catalog
for _row in seal_quest_catalog()['reward_definitions']+region_quest_catalog().data['reward_definitions']+story_quest_catalog()['reward_definitions']+job_quest_catalog()['reward_definitions']:
 if _row['template'] in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_row['template']],TEMPLATE_BAG_GROUPS[_row['template']],TEMPLATE_MAX_STACKS[_row['template']])!=(_row['metadata'],_row['group'],_row['max_stack']):raise ValueError('Conflicting quest reward classification')
 VERIFIED_TEMPLATES[_row['template']]=_row['metadata']
 TEMPLATE_BAG_GROUPS[_row['template']]=_row['group']
 TEMPLATE_MAX_STACKS[_row['template']]=_row['max_stack']

from els_server.domain.tutorial_accessory import minime_reward_definition
_minime_reward=minime_reward_definition()
if _minime_reward['template'] in VERIFIED_TEMPLATES:raise ValueError('Conflicting original Minime reward registration')
VERIFIED_TEMPLATES[_minime_reward['template']]=_minime_reward['metadata']
TEMPLATE_BAG_GROUPS[_minime_reward['template']]=_minime_reward['group']
TEMPLATE_MAX_STACKS[_minime_reward['template']]=_minime_reward['max_stack']

from els_server.domain.travel_pass import definition as travel_pass_definition
_pass=travel_pass_definition()
VERIFIED_TEMPLATES[_pass['template']]=_pass['metadata']
TEMPLATE_BAG_GROUPS[_pass['template']]=_pass['group']
TEMPLATE_MAX_STACKS[_pass['template']]=_pass['max_stack']

from els_server.domain.pet_progression import catalog as pet_progression_catalog
for _row in pet_progression_catalog()['definitions']:
 if _row['template'] in VERIFIED_TEMPLATES:
  if (VERIFIED_TEMPLATES[_row['template']],TEMPLATE_BAG_GROUPS[_row['template']])!=(_row['metadata'],_row['group']):raise ValueError('Conflicting pet feed classification')
  continue
 VERIFIED_TEMPLATES[_row['template']]=_row['metadata']
 TEMPLATE_BAG_GROUPS[_row['template']]=_row['group']
 TEMPLATE_MAX_STACKS[_row['template']]=_row['max_stack']

from els_server.domain.pet_support import catalog as pet_support_catalog
for _row in pet_support_catalog()['definitions']:
 if _row['template'] in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_row['template']],TEMPLATE_BAG_GROUPS[_row['template']],TEMPLATE_MAX_STACKS[_row['template']])!=(_row['metadata'],_row['group'],_row['max_stack']):raise ValueError('Conflicting pet support classification')
 VERIFIED_TEMPLATES[_row['template']]=_row['metadata']
 TEMPLATE_BAG_GROUPS[_row['template']]=_row['group']
 TEMPLATE_MAX_STACKS[_row['template']]=_row['max_stack']

@functools.lru_cache(maxsize=1)
def fixture():
 c=json.loads((BASE/'item-body-candidate.json').read_text(encoding='utf8'))
 p=json.loads((BASE/'private-item-body-verification.json').read_text(encoding='utf8'))
 if c['client_sha256']!=CLIENT_SHA or c['reader']!='0xd9a550' or p.get('ok')!=1 or p.get('size')!=304 or p.get('consumed')!=304 or p.get('fields_match') is not True or p.get('native_template_id')!=77000 or p.get('native_name')!='初级体力药水' or p.get('applied_to_game') is not False:raise ValueError('Native item fixture verification mismatch')
 if hashlib.sha256((BASE/'decompiled/0xd9a550.c').read_bytes()).hexdigest()!=c['source_sha256']:raise ValueError('Reviewed item reader changed')
 return c

from els_server.domain.repair_pass import definition as repair_pass_definition
_pass=repair_pass_definition()
VERIFIED_TEMPLATES[_pass['template']]=_pass['metadata']
TEMPLATE_BAG_GROUPS[_pass['template']]=_pass['group']
TEMPLATE_MAX_STACKS[_pass['template']]=_pass['max_stack']
from els_server.domain.decomposition_rules import reward_definition as decomposition_reward_definition
_crystal=decomposition_reward_definition()
VERIFIED_TEMPLATES[_crystal['template']]=_crystal['metadata']
TEMPLATE_BAG_GROUPS[_crystal['template']]=_crystal['group']
TEMPLATE_MAX_STACKS[_crystal['template']]=_crystal['max_stack']

from els_server.domain.equipment_ui_materials import definitions as equipment_ui_materials
for _material in equipment_ui_materials().values():
 VERIFIED_TEMPLATES[_material['template']]=_material['metadata']
 TEMPLATE_BAG_GROUPS[_material['template']]=_material['group']
 TEMPLATE_MAX_STACKS[_material['template']]=_material['max_stack']
from els_server.domain.identification_ui import catalog as identification_ui_catalog
for _material in identification_ui_catalog()['materials'].values():
 VERIFIED_TEMPLATES[_material['template']]=_material['metadata']
 TEMPLATE_BAG_GROUPS[_material['template']]=_material['group']
 TEMPLATE_MAX_STACKS[_material['template']]=_material['max_stack']

from els_server.domain.fixed_cubes import catalog as fixed_cube_catalog
from els_server.domain.regional_boss_cubes import data as regional_boss_cube_data
for _row in regional_boss_cube_data()['items'].values():
 if _row['template'] in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_row['template']],TEMPLATE_BAG_GROUPS[_row['template']],TEMPLATE_MAX_STACKS[_row['template']])!=(_row['metadata'],_row['group'],_row['max_stack']):raise ValueError('Conflicting boss cube item')
 VERIFIED_TEMPLATES[_row['template']]=_row['metadata']
 TEMPLATE_BAG_GROUPS[_row['template']]=_row['group']
 TEMPLATE_MAX_STACKS[_row['template']]=_row['max_stack']
for _cube in fixed_cube_catalog().values():
 if _cube['template'] in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_cube['template']],TEMPLATE_BAG_GROUPS[_cube['template']],TEMPLATE_MAX_STACKS[_cube['template']])!=(_cube['metadata'],4,99):raise ValueError('Conflicting fixed cube item')
 VERIFIED_TEMPLATES[_cube['template']]=_cube['metadata']
 TEMPLATE_BAG_GROUPS[_cube['template']]=4
 TEMPLATE_MAX_STACKS[_cube['template']]=99
from els_server.domain.apple_consumables import inventory_definitions as apple_definitions
for _row in apple_definitions():
 if _row['template'] in VERIFIED_TEMPLATES:raise ValueError('Conflicting apple inventory template')
 VERIFIED_TEMPLATES[_row['template']]=_row['metadata']
 TEMPLATE_BAG_GROUPS[_row['template']]=_row['group']
 TEMPLATE_MAX_STACKS[_row['template']]=_row['max_stack']
from els_server.domain.select_cubes import catalog as select_cube_catalog
for _cube in select_cube_catalog().values():
 if _cube['template'] in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_cube['template']],TEMPLATE_BAG_GROUPS[_cube['template']],TEMPLATE_MAX_STACKS[_cube['template']])!=(_cube['metadata'],4,99):raise ValueError('Conflicting selection cube item')
 VERIFIED_TEMPLATES[_cube['template']]=_cube['metadata']
 TEMPLATE_BAG_GROUPS[_cube['template']]=4
 TEMPLATE_MAX_STACKS[_cube['template']]=99

from els_server.domain.companion_fashion import resolve_slots as companion_fashion_slots
FASHION_EQUIP_SLOTS = companion_fashion_slots(FASHION_EQUIP_SLOTS)

from els_server.domain.advanced_enhancement_materials import catalog as advanced_enhancement_material_catalog
ADVANCED_TIMED_TEMPLATES=frozenset(r['template'] for r in advanced_enhancement_material_catalog()['items'] if r['requires_explicit_deadline'])
for _row in advanced_enhancement_material_catalog()['items']:
 if _row['template'] in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_row['template']],TEMPLATE_BAG_GROUPS[_row['template']])!=(_row['metadata'],4):raise ValueError('Conflicting advanced enhancement material')
 VERIFIED_TEMPLATES[_row['template']]=_row['metadata']
 TEMPLATE_BAG_GROUPS[_row['template']]=4
 TEMPLATE_MAX_STACKS[_row['template']]=99

from els_server.domain.atma_sockets import catalog as atma_socket_catalog
for _row in atma_socket_catalog()['items'].values():
 if _row['template'] in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_row['template']],TEMPLATE_BAG_GROUPS[_row['template']],TEMPLATE_MAX_STACKS[_row['template']])!=(_row['metadata'],4,_row['max_stack']):raise ValueError('Conflicting Atma stone')
 VERIFIED_TEMPLATES[_row['template']]=_row['metadata']
 TEMPLATE_BAG_GROUPS[_row['template']]=4
 TEMPLATE_MAX_STACKS[_row['template']]=_row['max_stack']

from els_server.domain.additional_magic_stones import catalog as additional_magic_stone_catalog
for _row in additional_magic_stone_catalog()['items'].values():
 if _row['template'] in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_row['template']],TEMPLATE_BAG_GROUPS[_row['template']],TEMPLATE_MAX_STACKS[_row['template']])!=(_row['metadata'],4,_row['max_stack']):raise ValueError('Conflicting additional magic stone')
 VERIFIED_TEMPLATES[_row['template']]=_row['metadata']
 TEMPLATE_BAG_GROUPS[_row['template']]=4
 TEMPLATE_MAX_STACKS[_row['template']]=_row['max_stack']

from els_server.domain.manufacture_rules import inventory_definitions as manufacture_inventory_definitions, inventory_fashion_records, inventory_fashion_position
from els_server.domain.companion_fashion import resolve_slots_from_records
_manufacture_fashion_records=inventory_fashion_records()
for _row in manufacture_inventory_definitions().values():
 if _row['template'] not in VERIFIED_TEMPLATES:
  VERIFIED_TEMPLATES[_row['template']]=_row['metadata']
  TEMPLATE_BAG_GROUPS[_row['template']]=_row['group']
  TEMPLATE_MAX_STACKS[_row['template']]=_row['max_stack']
 if _row['group'] in (7,27):
  _position=inventory_fashion_position(_manufacture_fashion_records[_row['template']])
  if _position in FASHION_POSITIONS and _row['template'] not in FASHION_EQUIP_SLOTS:
   FASHION_EQUIP_SLOTS.update(resolve_slots_from_records({_row['template']:FASHION_POSITIONS[_position]}, {_row['template']:_manufacture_fashion_records[_row['template']][0]}))
del _manufacture_fashion_records

from els_server.domain.titles import catalog as title_catalog
for _title_item in title_catalog()['items'].values():
 if _title_item['template'] in VERIFIED_TEMPLATES:
  if (VERIFIED_TEMPLATES[_title_item['template']],TEMPLATE_BAG_GROUPS[_title_item['template']])!=(_title_item['metadata'],4):raise ValueError('Conflicting title item classification')
  continue
 VERIFIED_TEMPLATES[_title_item['template']]=_title_item['metadata']
 TEMPLATE_BAG_GROUPS[_title_item['template']]=4
 TEMPLATE_MAX_STACKS[_title_item['template']]=99
from els_server.domain.artifact_progression import catalog as artifact_catalog,slots as artifact_slots
for _row in artifact_catalog()['definitions']:
 if _row['template'] in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_row['template']],TEMPLATE_BAG_GROUPS[_row['template']],TEMPLATE_MAX_STACKS[_row['template']])!=(_row['metadata'],_row['group'],_row['max_stack']):raise ValueError('Conflicting Artifact inventory definition')
 VERIFIED_TEMPLATES[_row['template']]=_row['metadata']
 TEMPLATE_BAG_GROUPS[_row['template']]=_row['group']
 TEMPLATE_MAX_STACKS[_row['template']]=_row['max_stack']

from els_server.domain.item_sealing_rules import definitions as item_sealing_definitions
for _stamp in item_sealing_definitions().values():
 if _stamp['template'] in VERIFIED_TEMPLATES:
  if (VERIFIED_TEMPLATES[_stamp['template']],TEMPLATE_BAG_GROUPS[_stamp['template']],TEMPLATE_MAX_STACKS[_stamp['template']])!=(_stamp['metadata'],4,99):raise ValueError('Conflicting original seal stamp definition')
  continue
 VERIFIED_TEMPLATES[_stamp['template']]=_stamp['metadata']
 TEMPLATE_BAG_GROUPS[_stamp['template']]=4
 TEMPLATE_MAX_STACKS[_stamp['template']]=99

from els_server.domain.fashion_singles import definitions as standalone_fashion_definitions
for _row in standalone_fashion_definitions():
 if _row['template'] in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_row['template']],TEMPLATE_BAG_GROUPS[_row['template']],TEMPLATE_MAX_STACKS[_row['template']])!=(_row['metadata'],_row['group'],1):raise ValueError('Conflicting standalone fashion definition')
 if _row['template'] in FASHION_EQUIP_SLOTS and FASHION_EQUIP_SLOTS[_row['template']]!=_row['equipment_slot']:raise ValueError('Conflicting standalone fashion slot')
 VERIFIED_TEMPLATES[_row['template']]=_row['metadata']
 TEMPLATE_BAG_GROUPS[_row['template']]=_row['group']
 TEMPLATE_MAX_STACKS[_row['template']]=1
 FASHION_EQUIP_SLOTS[_row['template']]=_row['equipment_slot']

# Native verified source tickets; 99 is the local storage stack policy.
from els_server.domain.event_dungeons import catalog as event_dungeon_catalog
for _key,_row in event_dungeon_catalog()['tickets'].items():
 _template=int(_key);_expected=(_row['metadata'],_row['bag_group'],99)
 if _template in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_template],TEMPLATE_BAG_GROUPS[_template],TEMPLATE_MAX_STACKS[_template])!=_expected:raise ValueError('Conflicting event ticket definition')
 VERIFIED_TEMPLATES[_template],TEMPLATE_BAG_GROUPS[_template],TEMPLATE_MAX_STACKS[_template]=_expected

from els_server.domain.equipment_chip_rules import catalog as _chip_catalog
_chip_registration=_chip_catalog()['material']
VERIFIED_TEMPLATES[_chip_registration['template']]=_chip_registration['metadata']
TEMPLATE_BAG_GROUPS[_chip_registration['template']]=_chip_registration['group']
TEMPLATE_MAX_STACKS[_chip_registration['template']]=_chip_registration['max_stack']

from els_server.domain.equipment_chip_reset_items import catalog as _chip_reset_items
for _reset_item in _chip_reset_items()['items'].values():
 _t=_reset_item['template'];_expected=(_reset_item['metadata'],_reset_item['group'],_reset_item['source_max_stack'])
 if _t in VERIFIED_TEMPLATES:
  if (VERIFIED_TEMPLATES[_t],TEMPLATE_BAG_GROUPS[_t])!=_expected[:2]:raise ValueError('Conflicting reset ticket registration')
  continue
 VERIFIED_TEMPLATES[_t],TEMPLATE_BAG_GROUPS[_t],TEMPLATE_MAX_STACKS[_t]=_expected


from els_server.domain.equipment_reforge_rules import catalog as _reforge_catalog
for _reforge_material in _reforge_catalog()['materials'].values():
 _t=_reforge_material['template']
 if _t in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_t],TEMPLATE_BAG_GROUPS[_t])!=(_reforge_material['metadata'],_reforge_material['group']):raise ValueError('Conflicting finite reforge material')
 if _t in VERIFIED_TEMPLATES:continue
 VERIFIED_TEMPLATES[_t]=_reforge_material['metadata']
 TEMPLATE_BAG_GROUPS[_t]=_reforge_material['group']
 TEMPLATE_MAX_STACKS[_t]=_reforge_material['max_stack']

from els_server.domain.equipment_engrave_rules import catalog as _engrave_catalog
for _engrave_material in _engrave_catalog()['materials'].values():
 _t=_engrave_material['template']
 if _t in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_t],TEMPLATE_BAG_GROUPS[_t])!=(_engrave_material['metadata'],_engrave_material['group']):raise ValueError('Conflicting finite engraving material')
 if _t in VERIFIED_TEMPLATES:continue
 VERIFIED_TEMPLATES[_t]=_engrave_material['metadata']
 TEMPLATE_BAG_GROUPS[_t]=_engrave_material['group']
 TEMPLATE_MAX_STACKS[_t]=_engrave_material['max_stack']

# User-local color vouchers: native bag4, one coupon and zero ED per use.
from els_server.domain.exascale_color_inventory import definitions as _color_vouchers
for _row in _color_vouchers():
 if _row['template'] in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_row['template']],TEMPLATE_BAG_GROUPS[_row['template']],TEMPLATE_MAX_STACKS[_row['template']])!=(_row['metadata'],4,999):raise ValueError('Conflicting color voucher definition')
 VERIFIED_TEMPLATES[_row['template']]=_row['metadata']
 TEMPLATE_BAG_GROUPS[_row['template']]=4
 TEMPLATE_MAX_STACKS[_row['template']]=999

# Exact official Essence pouch; original metadata/flags and output cap1000.
from els_server.domain.ep_essence_bag import definitions as _essence_pouch_items
for _row in _essence_pouch_items():
 if _row['template'] in VERIFIED_TEMPLATES:raise ValueError('Conflicting Essence pouch item')
 VERIFIED_TEMPLATES[_row['template']]=_row['metadata']
 TEMPLATE_BAG_GROUPS[_row['template']]=_row['group']
 TEMPLATE_MAX_STACKS[_row['template']]=_row['max_stack']

# Exact current-source manual magic potion; no acquisition provider is opened.
from els_server.domain.consumables import manual_magic_potion_definition
_manual_magic=manual_magic_potion_definition()
_t=_manual_magic['template'];_expected=(_manual_magic['metadata'],_manual_magic['group'],_manual_magic['max_stack'])
if _t in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_t],TEMPLATE_BAG_GROUPS[_t],TEMPLATE_MAX_STACKS[_t])!=_expected:raise ValueError('Conflicting manual magic potion definition')
VERIFIED_TEMPLATES[_t],TEMPLATE_BAG_GROUPS[_t],TEMPLATE_MAX_STACKS[_t]=_expected

# Four exact permanent EP pet acquisition items; no pet activation producer.
from els_server.domain.ep_pets import definitions as _ep_pet_items
for _row in _ep_pet_items():
 if _row['template'] in VERIFIED_TEMPLATES:raise ValueError('Conflicting EP pet inventory definition')
 VERIFIED_TEMPLATES[_row['template']]=_row['metadata']
 TEMPLATE_BAG_GROUPS[_row['template']]=_row['group']
 TEMPLATE_MAX_STACKS[_row['template']]=_row['max_stack']

# User policy (2026-10-18): raise existing stackable items to at least 999.
# Original catalog evidence stays immutable. Equipment/singletons stay at one;
# native material stacks already above 999 retain their larger limits.
for _template,_source_limit in tuple(TEMPLATE_MAX_STACKS.items()):
 if 1<_source_limit<LOCAL_MAX_STACK:TEMPLATE_MAX_STACKS[_template]=LOCAL_MAX_STACK

# Newly qualified ED coupons keep their native500 cap; existing999 policy above
# remains unchanged for all previously admitted items.
from els_server.domain.equipment_reforge_coupons import definitions as _reforge_coupons
for _row in _reforge_coupons():
 _t=_row['template'];_expected=(_row['metadata'],_row['group'],_row['max_stack'])
 if _t in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_t],TEMPLATE_BAG_GROUPS[_t],TEMPLATE_MAX_STACKS[_t])!=_expected:raise ValueError('Conflicting reforge coupon definition')
 VERIFIED_TEMPLATES[_t],TEMPLATE_BAG_GROUPS[_t],TEMPLATE_MAX_STACKS[_t]=_expected

# Saved ordinary accessories use the existing native metadata0 DTO. New sources
# remain separately gated in acquisition_policy; registration never grants items.
from els_server.domain.ordinary_accessories import definitions as ordinary_accessory_definitions
for _row in ordinary_accessory_definitions().values():
 if _row['template'] in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_row['template']],TEMPLATE_BAG_GROUPS[_row['template']],TEMPLATE_MAX_STACKS[_row['template']])!=(_row['metadata'],2,1):raise ValueError('Conflicting ordinary accessory definition')
 VERIFIED_TEMPLATES[_row['template']]=_row['metadata']
 TEMPLATE_BAG_GROUPS[_row['template']]=2
 TEMPLATE_MAX_STACKS[_row['template']]=1

from els_server.domain.resonance import book_definitions as resonance_book_definitions
for _row in resonance_book_definitions():
 VERIFIED_TEMPLATES[_row['template']]=_row['metadata']
 TEMPLATE_BAG_GROUPS[_row['template']]=_row['group']
 TEMPLATE_MAX_STACKS[_row['template']]=_row['max_stack']

from els_server.domain.wardrobe_extensions import catalog as wardrobe_extensions_catalog
for _key,_row in wardrobe_extensions_catalog()['consumables'].items():
 _t=int(_key);_expected=(_row['metadata'],_row['group'],_row['max_stack'])
 if _t in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_t],TEMPLATE_BAG_GROUPS[_t],TEMPLATE_MAX_STACKS[_t])!=_expected:raise ValueError('Conflicting wardrobe source classification')
 VERIFIED_TEMPLATES[_t],TEMPLATE_BAG_GROUPS[_t],TEMPLATE_MAX_STACKS[_t]=_expected

# First plain-red transfer subset: exactly one already-owned ticket instance.
# This is a bounded compatibility limit, not an asserted native stack maximum.
from els_server.domain.equipment_spell_rules import ticket_definitions as _spell_tickets
for _row in _spell_tickets():
 _t=_row['template'];_expected=(_row['metadata'],_row['group'],_row['max_stack'])
 if _t in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_t],TEMPLATE_BAG_GROUPS[_t],TEMPLATE_MAX_STACKS[_t])!=_expected:raise ValueError('Conflicting plain red transfer ticket')
 VERIFIED_TEMPLATES[_t],TEMPLATE_BAG_GROUPS[_t],TEMPLATE_MAX_STACKS[_t]=_expected

from els_server.domain.purifier_exchange_rules import inventory_definitions as purifier_inventory_definitions
for _row in purifier_inventory_definitions():
 _t=_row['template'];_expected=(_row['metadata'],_row['group'],_row['max_stack'])
 if _t in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_t],TEMPLATE_BAG_GROUPS[_t],TEMPLATE_MAX_STACKS[_t])!=_expected:raise ValueError('Conflicting purifier exchange inventory definition')
 VERIFIED_TEMPLATES[_t],TEMPLATE_BAG_GROUPS[_t],TEMPLATE_MAX_STACKS[_t]=_expected

# Newly admitted old-owned blessed elixirs keep their qualified99 cap, after
# the historical999 compatibility loop; no new global stack rule is inferred.
from els_server.domain.elixir_items import inventory_definitions as elixir_definitions
for _row in elixir_definitions():
 if _row['template'] in VERIFIED_TEMPLATES:raise ValueError('Conflicting elixir inventory template')
 VERIFIED_TEMPLATES[_row['template']]=_row['metadata']
 TEMPLATE_BAG_GROUPS[_row['template']]=_row['group']
 TEMPLATE_MAX_STACKS[_row['template']]=_row['max_stack']

# Only newly admitted723603 keeps its source-qualified99 after old999 policy.
if select_cube_catalog()[723603]['max_stack']!=99:raise ValueError('Elixir box stack source')
TEMPLATE_MAX_STACKS[723603]=99

# One account-once native53520 reward, bounded to one unstacked instance.
# Evidence is static same-client record + reviewed304 codec/private roundtrip,
# deliberately not a fabricated native-execution receipt.
from els_server.domain.erp_support_quest import item_definition as erp_support_item
_erp_support=erp_support_item();_t=_erp_support['template']
if _t in VERIFIED_TEMPLATES:raise ValueError('Conflicting ERP support reward')
VERIFIED_TEMPLATES[_t]=_erp_support['metadata'];TEMPLATE_BAG_GROUPS[_t]=_erp_support['group'];TEMPLATE_MAX_STACKS[_t]=_erp_support['max_stack']

from els_server.domain.cartridge_registration_rules import materials as cartridge_materials
for _row in cartridge_materials():
 _t=_row['template'];_expected=(_row['metadata'],_row['group'],_row['max_stack'])
 if _t in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_t],TEMPLATE_BAG_GROUPS[_t],TEMPLATE_MAX_STACKS[_t])!=_expected:raise ValueError('Conflicting Cartridge material inventory definition')
 VERIFIED_TEMPLATES[_t],TEMPLATE_BAG_GROUPS[_t],TEMPLATE_MAX_STACKS[_t]=_expected

# Existing119335 is read through a private exact adapter, never a generic new grant.
from els_server.domain.cartridge_selection_box import BOX as cartridge_box_template
if cartridge_box_template in VERIFIED_TEMPLATES or cartridge_box_template in TEMPLATE_BAG_GROUPS or cartridge_box_template in TEMPLATE_MAX_STACKS:raise ValueError("Conflicting private Cartridge box admission")
# These two entries only disable split/merge and retain the known bag mapping.
# No VERIFIED_TEMPLATES entry: even source-flag bypasses cannot create this box.
TEMPLATE_BAG_GROUPS[cartridge_box_template]=4
TEMPLATE_MAX_STACKS[cartridge_box_template]=1

from els_server.domain.wardrobe_ticket_box import BOX as wardrobe_box_template
if wardrobe_box_template in VERIFIED_TEMPLATES or wardrobe_box_template in TEMPLATE_BAG_GROUPS or wardrobe_box_template in TEMPLATE_MAX_STACKS:raise ValueError("Conflicting existing wardrobe box reader")
TEMPLATE_BAG_GROUPS[wardrobe_box_template]=4
TEMPLATE_MAX_STACKS[wardrobe_box_template]=1

# Existing ERP potion readers confer no generic grant or merge authority.
from els_server.domain.erp_potions_existing import TEMPLATES as existing_erp_potions
for _t in existing_erp_potions:
 if _t in VERIFIED_TEMPLATES or _t in TEMPLATE_BAG_GROUPS or _t in TEMPLATE_MAX_STACKS:raise ValueError('Conflicting existing ERP potion reader')
 TEMPLATE_BAG_GROUPS[_t]=4
 TEMPLATE_MAX_STACKS[_t]=1  # disable ordinary split/merge; not a native stack cap

def validate_item(item):
 if isinstance(item,dict) and item.get('template')in existing_erp_potions:
  from els_server.domain.erp_potions_existing import validate_existing
  return validate_existing(item)
 if isinstance(item,dict) and item.get("template")==wardrobe_box_template:
  from els_server.domain.wardrobe_ticket_box import validate_existing_box
  return validate_existing_box(item)
 if isinstance(item,dict) and item.get('template')==cartridge_box_template:
  from els_server.domain.cartridge_selection_box import validate_existing_box
  return validate_existing_box(item)
 keys={'uid','template','metadata','count','group','slot'}
 if not isinstance(item,dict) or set(item)-{'attributes','durability','expires_at','enhancement','lock_until','option_groups','identified','enhancement_gauge','enhancement_guarantee','sealed','seal_used','artifact_socket_open','chip_tuning','reforge','appearance_template','wardrobe_hanger','dye_colors','appearance_colors','cartridge'}!=keys or any(type(item[k]) is not int for k in keys):raise ValueError('Invalid inventory item fields')
 if not 1<=item['uid']<2**63 or item['template'] not in VERIFIED_TEMPLATES or item['metadata']!=VERIFIED_TEMPLATES[item['template']]:raise ValueError('Invalid inventory item identity/template')
 if item['template'] in ADVANCED_TIMED_TEMPLATES and 'expires_at' not in item:raise ValueError('Timed enhancement material requires explicit expiration')
 from els_server.game_data import client_data
 definition=client_data().item(item['template'])
 if definition['metadata']!=item['metadata']:raise ValueError('Item does not match current client definition')
 equipped=item['group']==9 and item['template'] in FASHION_EQUIP_SLOTS and item['slot']==FASHION_EQUIP_SLOTS[item['template']]
 if item['group']==9 and item['template'] in normal_equipment_definitions():
  from els_server.domain.equipment_requirements import catalog as requirements
  equipped=item['slot']==requirements()[1][definition['equip_position']]
 if item['template'] in ordinary_accessory_definitions():
  from els_server.domain.ordinary_accessories import accepts_equipped
  equipped=accepts_equipped(item)
 if item['group']==24:equipped=item['slot'] in artifact_slots(item['template'])
 from els_server.domain.bag_capacity import wire_limit
 bag=item['group']==TEMPLATE_BAG_GROUPS[item['template']] and 0<=item['slot']<wire_limit(item['group'])
 if not 1<=item['count']<=TEMPLATE_MAX_STACKS[item['template']] or not (equipped or bag):raise ValueError('Invalid local inventory count/slot')
 result=dict(item)
 if 'cartridge'in item:
  from els_server.domain.cartridge_registration_rules import scalar,binding_catalog
  result['cartridge']=scalar(item['cartridge'])
  if result['cartridge']!=[0,0]and(item['template']not in binding_catalog()or item['group']not in(1,9)or item['count']!=1):raise ValueError('Cartridge projected carrier shape')
 if 'dye_colors'in item or 'appearance_colors'in item:
  from els_server.domain.wardrobe_extensions import color_state
  color_state(item)
 if 'appearance_template' in item or 'wardrobe_hanger' in item:
  from els_server.domain.wardrobe import validate_state
  validate_state(item)
 if 'lock_until' in item:
  from els_server.domain.item_locks import validate as validate_lock
  result['lock_until']=validate_lock(item['lock_until'])
 if item['template']==_pass['template'] and 'expires_at' not in item:raise ValueError('Repair pass requires an explicit expiration')
 if 'expires_at' in item:
  from els_server.domain.item_expiration import validate as validate_expiration
  result['expires_at']=validate_expiration(item['expires_at'])
 if 'durability' in item:
  from els_server.domain.equipment_durability import validate as validate_durability
  result['durability']=validate_durability(item['template'],item['durability'])
  if item['count']!=1:raise ValueError('Durable equipment cannot stack')
 if 'enhancement' in item:
  from els_server.domain.equipment_enhancement import validate as validate_enhancement
  result['enhancement']=validate_enhancement(item['template'],item['enhancement'])
  if item['count']!=1:raise ValueError('Enhanced equipment cannot stack')
 if 'attributes' in item:
  from els_server.domain.equipment_attributes import validate_slots
  result['attributes']=validate_slots(item['template'],item['attributes'])
  if item['count']!=1:raise ValueError('Attributed equipment cannot stack')
 if 'option_groups' in item:
  from els_server.domain.sage_sockets import validate as validate_options
  result['option_groups']=validate_options(item['template'],item['option_groups'])
  if item['count']!=1:raise ValueError('Socket equipment cannot stack')
 if item['template']==_chip_registration['template']:
  from els_server.domain.equipment_chip_rules import source_options
  if set(item.get('option_groups',{}))!={'1'}:raise ValueError('Chip requires its generated native base options')
  source_options(item['option_groups']['1'])
 if 'chip_tuning' in item:
  from els_server.domain.equipment_chip_rules import state as chip_state
  result['chip_tuning']=chip_state(item['template'],item['chip_tuning'])
  if item['count']!=1:raise ValueError('Chip state cannot stack')
 if 'reforge' in item:
  from els_server.domain.equipment_reforge_rules import state as reforge_state
  result['reforge']=reforge_state(item['template'],item['reforge'])
 from els_server.domain.equipment_reforge_rules import validate_instance as validate_reforge
 validate_reforge(result)
 if 'identified' in item:
  from els_server.domain.identification_ui import require_template
  require_template(item['template'])
  if type(item['identified']) is not bool or item['count']!=1:raise ValueError('Invalid identification flag/count')
  if not item['identified']:
   from els_server.domain.artifact_identification import supported,unidentified_values
   values=item.get('option_groups',{}).get('1',[])
   if not (unidentified_values(item['template'],values) if supported(item['template']) else not any(values)):raise ValueError('Invalid unidentified options')
 if 'artifact_socket_open' in item:
  from els_server.domain.artifact_progression import slots as artifact_equipment_slots
  if type(item['artifact_socket_open']) is not bool or not artifact_equipment_slots(item['template']) or item['count']!=1:raise ValueError('Artifact spirit-slot flag')
  result['artifact_socket_open']=item['artifact_socket_open']
 if 'enhancement_gauge' in item or 'enhancement_guarantee' in item:
  from els_server.domain.enhancement_progress import validate as validate_progress
  gauge,points=validate_progress(item)
  if gauge:result['enhancement_gauge']=gauge
  if points:result['enhancement_guarantee']=points
 if 'sealed' in item or 'seal_used' in item:
  from els_server.storage.item_seals import validate as validate_seals
  validate_seals(item.get('sealed',False),item.get('seal_used',0))
  result.update(sealed=item.get('sealed',False),seal_used=item.get('seal_used',0))
 return result
def item_body(item):
 item=validate_item(item);c=fixture();data=bytearray.fromhex(c['wire_hex'])
 if item['template']==_chip_registration['template']:
  from els_server.domain.equipment_chip_rules import source_options
  source_options(item.get('option_groups',{}).get('1',[]))
 for f in c['fields']:
  off=int(f['offset'],0);wire=f['wire_offset']
  if off==0:struct.pack_into('>I',data,wire,item['template'])
  elif off==4:data[wire]=item['metadata']
  elif off==5:struct.pack_into('>i',data,wire,item['count'])
  elif off==9 and 'durability' in item:struct.pack_into('>h',data,wire,item['durability'])
  elif off==11:data[wire]=item.get('seal_used',0)+(100 if item.get('sealed',False) else 0)
  elif off==12 and 'enhancement' in item:struct.pack_into('>b',data,wire,item['enhancement'])
  elif off==0x3a8 and 'enhancement_gauge' in item:struct.pack_into('>i',data,wire,item['enhancement_gauge'])
  elif off==0x3ac and 'enhancement_guarantee' in item:struct.pack_into('>i',data,wire,item['enhancement_guarantee'])
  elif off==0x34d and 'identified' in item:data[wire]=0 if item['identified'] else 2
  elif off==0x3a7 and 'artifact_socket_open' in item:data[wire]=int(item['artifact_socket_open'])
  elif 0x3b0<=off<=0x3b3 and 'chip_tuning' in item:data[wire]=item['chip_tuning'][off-0x3b0]
  elif off in (0x397,0x39b,0x39f) and 'reforge' in item:struct.pack_into('>i',data,wire,item['reforge'][(off-0x397)//4])
  elif off==0x370 and 'lock_until' in item:struct.pack_into('>Q',data,wire,item['lock_until'])
  elif off==0x3ec:struct.pack_into('>ii',data,wire,*item.get('cartridge',[0,0]))
  elif off==0x378:struct.pack_into('>i',data,wire,item.get('appearance_template',0))
  elif off==0x37c:data[wire]=int(item.get('wardrobe_hanger',False))
  elif off in (0x37d,0x389):struct.pack_into('>Iiii',data,wire,3,*item.get('dye_colors'if off==0x37d else'appearance_colors',[0,0,0]))
 if len(data)!=304:raise ValueError('Native item body bound')
 if 'expires_at' in item:
  from els_server.domain.item_expiration import date_string
  field=next(f for f in c['fields'] if int(f['offset'],0)==0x350)
  pos=field['wire_offset'];raw=date_string(item['expires_at']).encode('utf-16le')
  if data[pos:pos+4]!=bytes(4):raise ValueError('Native expiry string seed changed')
  data[pos:pos+4]=struct.pack('>I',len(raw))+raw
 if item.get('option_groups'):
  field=next(f for f in c['fields'] if int(f['offset'],0)==0x25)
  pos=field['wire_offset']
  if data[pos:pos+136]!=struct.pack('>I',33)+bytes(132):raise ValueError('Native socket array seed changed')
  groups=item['option_groups']
  data[pos:pos+136]=struct.pack('>I',33)+b''.join(struct.pack('>I',len(groups.get(str(n),[])))+b''.join(struct.pack('>i',v) for v in groups.get(str(n),[])) for n in range(33))
 if any(item.get('attributes',())):
  field=next(f for f in c['fields'] if int(f['offset'],0)==0xd)
  pos=field['wire_offset']
  if data[pos:pos+4]!=bytes(4):raise ValueError('Native attribute vector seed changed')
  data[pos:pos+4]=struct.pack('>I4i',4,*item['attributes'])
 return bytes(data)
def inventory_payload(items):
 from els_server.domain.bag_capacity import wire_limit
 from els_server.domain.equipment_requirements import catalog as requirements
 if not isinstance(items,list) or len(items)>sum(wire_limit(g) for g in set(TEMPLATE_BAG_GROUPS.values()))+len(set(FASHION_EQUIP_SLOTS.values())|set(requirements()[1].values())|{s for r in ordinary_accessory_definitions().values() for s in r['slots']}):raise ValueError('Inventory list bound')
 checked=[validate_item(i) for i in items]
 if len({i['uid'] for i in checked})!=len(checked) or len({(i['group'],i['slot']) for i in checked})!=len(checked):raise ValueError('Duplicate inventory UID/slot')
 return struct.pack('>I',len(checked))+b''.join(struct.pack('>QBh',i['uid'],i['group'],i['slot'])+item_body(i)+b'\0'+bytes(8) for i in sorted(checked,key=lambda v:(v['group'],v['slot'])))

def inventory_restore_map(items):
 """2A/DA3370 +5B1: map<UID, inventory record>, restored without NEW.

 DB3490/DD3980 read the key and DB4F80 record. 1385780 -> 1984840
 inserts with mark-new=false, unlike D9 -> 197DAD0.
 """
 inventory_payload(items)  # Validate identities and slots before serializing.
 bag=sorted((i for i in items if i['group'] not in (9,24)),key=lambda i:i['uid'])
 return struct.pack('>I',len(bag))+b''.join(
     struct.pack('>QQBh',i['uid'],i['uid'],i['group'],i['slot'])+
     item_body(i)+bytes(9) for i in bag)


from els_server.domain.cartridge_exchange_rules import source_definition as cartridge_exchange_source
_cartridge_exchange_source=cartridge_exchange_source();_t=_cartridge_exchange_source["template"]
if _t in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_t],TEMPLATE_BAG_GROUPS[_t],TEMPLATE_MAX_STACKS[_t])!=(2,3,1000):raise ValueError("Conflicting black-fragment reader")
VERIFIED_TEMPLATES[_t]=2;TEMPLATE_BAG_GROUPS[_t]=3;TEMPLATE_MAX_STACKS[_t]=1000


# Current118204 Sturdy Mithril reader only; no source or grant is introduced.
# Same native type6/SORT_TYPE.ST_MATERIAL3 path as deployed701000; record+10
# is the current1000 stack cap, above the existing999 compatibility floor.
from els_server.game_data import client_data as _smith_client_data
_smith_material=_smith_client_data().item(118204)
if (_smith_material['item_type'],_smith_material['metadata'],struct.unpack_from('<I',_smith_material['record'],0x10)[0])!=(6,2,1000) or hashlib.sha256(_smith_material['record']).hexdigest()!='35a2511b9161e41d6675d3111e99b2b4815ec2c898e9362ecb5c0d620de898b1':raise ValueError('Current smith material reader source')
if 118204 in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[118204],TEMPLATE_BAG_GROUPS[118204],TEMPLATE_MAX_STACKS[118204])!=(2,3,1000):raise ValueError('Conflicting current smith material reader')
VERIFIED_TEMPLATES[118204]=2;TEMPLATE_BAG_GROUPS[118204]=3;TEMPLATE_MAX_STACKS[118204]=1000
# Current Flask accumulation rewards only: native type7, bag4, metadata2/cap500.
# Explicit current reward table; does not open another acquisition source.
from els_server.domain.flask_rules import special_inventory_definitions as _flask_bonus_definitions
for _flask_bonus in _flask_bonus_definitions():
 if _flask_bonus['template'] in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_flask_bonus['template']],TEMPLATE_BAG_GROUPS[_flask_bonus['template']],TEMPLATE_MAX_STACKS[_flask_bonus['template']])!=(_flask_bonus['metadata'],_flask_bonus['group'],_flask_bonus['max_stack']):raise ValueError('Conflicting current Flask bonus reader')
 VERIFIED_TEMPLATES[_flask_bonus['template']]=_flask_bonus['metadata']
 TEMPLATE_BAG_GROUPS[_flask_bonus['template']]=_flask_bonus['group']
 TEMPLATE_MAX_STACKS[_flask_bonus['template']]=_flask_bonus['max_stack']


# Finite native material admission; raw stack=0 means one nonstackable item.
# No acquisition channel added; preserve already admitted stack policies.
from els_server.domain.tenebros_rules import catalog as _tenebros_catalog
for _tid, _spec in _tenebros_catalog()["admission"].items():
 _tid=int(_tid)
 if _tid in VERIFIED_TEMPLATES:
  if (VERIFIED_TEMPLATES[_tid],TEMPLATE_BAG_GROUPS[_tid])!=(_spec["metadata"],_spec["group"]):raise ValueError("Tenebros material admission conflict")
  continue
 VERIFIED_TEMPLATES[_tid]=_spec["metadata"]
 TEMPLATE_BAG_GROUPS[_tid]=_spec["group"]
 TEMPLATE_MAX_STACKS[_tid]=max(1,_spec["max_stack"])
# Finite original AccountQuest reward readers. Keep unused712417 singleton;
#710105 retains current native300 after the earlier global compatibility floor.
# No item-use effect, timer, source other than the four exact quests, or old
# saved item migration is introduced here.
from els_server.domain.account_epic_quests import reward_item_definitions as _account_epic_reward_definitions
for _account_epic_reward in _account_epic_reward_definitions():
 _t=_account_epic_reward['template'];_expected=tuple(_account_epic_reward[k] for k in ('metadata','group','max_stack'))
 if _t in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_t],TEMPLATE_BAG_GROUPS[_t],TEMPLATE_MAX_STACKS[_t])!=_expected:raise ValueError('Conflicting finite account Epic reward reader')
 VERIFIED_TEMPLATES[_t],TEMPLATE_BAG_GROUPS[_t],TEMPLATE_MAX_STACKS[_t]=_expected

# Original26750 rewards: unused singleton instances only. Housing use is separate.
for _t,_digest,_flags in ((136034,'4376af863bbe3005333d2e4f2673780bc2a350bbd707fb4cab8ef595902f323d',4198410),(136039,'0567ac6833f56ac2722e347d7b0cd8b2d5d5ed6df70b3f71baaf0c53ea273398',4198402)):
 from els_server.game_data import client_data as _housing_reward_client_data
 _item=_housing_reward_client_data().item(_t)
 if (hashlib.sha256(_item['record']).hexdigest()!=_digest or (_item['item_type'],_item['metadata'],_item['flags4'],_item['flags8'],struct.unpack_from('<I',_item['record'],0x10)[0])!=(7,0,_flags,56,0)):raise ValueError('Original26750 reward item source')
 if _t in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_t],TEMPLATE_BAG_GROUPS[_t],TEMPLATE_MAX_STACKS[_t])!=(0,4,1):raise ValueError('Conflicting original26750 reward reader')
 VERIFIED_TEMPLATES[_t]=0;TEMPLATE_BAG_GROUPS[_t]=4;TEMPLATE_MAX_STACKS[_t]=1

# Exact32080 material and character PointMark reward readers; no new loot source.
for _t,_kind,_meta,_word,_digest in ((118357,7,2,500,'bd35c97bcefe8cae2c937d15fb2204808f6e9bf3d228187a2855f80784e2efbc'),(481315,14,0,0,'b8f0e7554e97b65265ad943b40e544d1497c74c67779f3e04cc439700918de48')):
 from els_server.game_data import client_data as _secret_reward_client_data
 _item=_secret_reward_client_data().item(_t)
 if (hashlib.sha256(_item['record']).hexdigest()!=_digest or (_item['item_type'],_item['metadata'],struct.unpack_from('<I',_item['record'],0x10)[0])!=(_kind,_meta,_word)):raise ValueError('Original32080 item source')
 _expected=(_meta,4,_word or 1)
 if _t in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_t],TEMPLATE_BAG_GROUPS[_t],TEMPLATE_MAX_STACKS[_t])!=_expected:raise ValueError('Conflicting original32080 reader')
 VERIFIED_TEMPLATES[_t],TEMPLATE_BAG_GROUPS[_t],TEMPLATE_MAX_STACKS[_t]=_expected

# Original26780 reward only: unused singleton713275, no housing/use state.
from els_server.game_data import client_data as _contract26780_client_data
_contract26780_item=_contract26780_client_data().item(713275)
if (hashlib.sha256(_contract26780_item['record']).hexdigest()!='3e05e84442189cbcd865e68a457cc7774aaa95d15bc45046fd90f23fb89977a1' or (_contract26780_item['item_type'],_contract26780_item['metadata'],_contract26780_item['flags4'],_contract26780_item['flags8'],struct.unpack_from('<I',_contract26780_item['record'],0x10)[0])!=(7,0,4198410,56,0)):raise ValueError('Original26780 reward item source')
if 713275 in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[713275],TEMPLATE_BAG_GROUPS[713275],TEMPLATE_MAX_STACKS[713275])!=(0,4,1):raise ValueError('Conflicting contract26780 reader')
VERIFIED_TEMPLATES[713275]=0;TEMPLATE_BAG_GROUPS[713275]=4;TEMPLATE_MAX_STACKS[713275]=1
