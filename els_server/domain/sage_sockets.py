"""Original base socket slots and official Sage stone outcomes."""
import functools,hashlib,json,struct
from pathlib import Path
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA,client_data
STONE=135184
@functools.lru_cache(maxsize=1)
def catalog():
 path=Path(__file__).resolve().parents[1]/'data/sage_sockets.json';raw=path.read_bytes()
 if hashlib.sha256(raw).hexdigest()!='d4a62b3d7ca911ebd36aa4760702eca667b63f7f1dcd8af8f784044bbdd982ad':raise ValueError('Sage source changed')
 c=json.loads(raw)
 if c['client_sha256']!=CLIENT_SHA or c['catalog_sha256']!=client_data().manifest['catalog_sha256']:raise ValueError('Sage client build mismatch')
 for source in c['sources']:
  if hashlib.sha256((PROJECT_ROOT/source['path']).read_bytes()).hexdigest()!=source['sha256']:raise ValueError('Sage evidence changed')
 return c
def capacity(template):
 d=client_data().item(template)
 if d['item_type'] not in (1,2) or d['flags4']&0xa0:raise ValueError('Unsupported socket equipment')
 catalog() # Also verifies the original custom Lua resource identity.
 from els_server.domain.socket_capacity import capacity as base_capacity
 n=base_capacity(template)
 if not n:raise ValueError('Original equipment has no base socket slots')
 return n
def validate(template,groups):
 if not isinstance(groups,dict) or set(groups)-{'9','10','11','12','0','1','13','14','15','16','18','19','20','21','25','27','28','29','31'}:raise ValueError('Unsupported option group')
 result={}
 for group,values in groups.items():
  if group in ('9','10','11','12'):
   from els_server.domain.equipment_spell_rules import options as spell_options
   result[group]=spell_options(template,int(group),values);continue
  if group=='25':
   from els_server.domain.boosting_2026_shadow import validate as validate_shadow
   result[group]=validate_shadow(template,values);continue
  if group=='13':
   from els_server.domain.equipment_reforge_rules import options as reforge_options
   result[group]=reforge_options(template,values);continue
  if group in ('14','15','16'):
   from els_server.domain.equipment_engrave_rules import options as engrave_options
   result[group]=engrave_options(template,int(group),values);continue
  if group=='27':
   from els_server.domain.equipment_chip_rules import armor_options
   result[group]=armor_options(template,values);continue
  if group=='29':
   from els_server.domain.option_conversion_existing import validate as validate_existing_conversion
   result[group]=validate_existing_conversion(template,values);continue
  if group=='28':
   from els_server.domain.equipment_circuit_rules import validate_grid
   result[group]=validate_grid(template,values);continue
  if group in ('18','19','20','21'):
   from els_server.domain.local_artifact_rules import spirit_group,validate_spirit
   if int(group)!=spirit_group(template):raise ValueError('Spirit category does not match Artifact part')
   result[group]=validate_spirit(template,values);continue
  if group=='31':
   from els_server.domain.artifact_conversion import validate as validate_conversion
   result[group]=validate_conversion(template,values);continue
  if group=='1':
   from els_server.domain.equipment_chip_rules import material as chip_material,source_options
   if chip_material(template):
    result[group]=source_options(values);continue
   from els_server.domain.equipment_circuit_rules import material,validate_material
   if material(template) is not None:
    result[group]=validate_material(template,values);continue
   from els_server.domain.identification_ui import validate as validate_identification
   result[group]=validate_identification(template,values);continue
  n=capacity(template)
  from els_server.domain.atma_sockets import valid_option
  from els_server.domain.additional_magic_stones import valid_option as valid_additional
  from els_server.domain.ordinary_magic_stones import valid_option as valid_ordinary
  if not isinstance(values,(list,tuple)) or len(values)!=n or any(type(v) is not int or v!=0 and str(v) not in catalog()['options'] and not valid_option(template,v) and not valid_additional(template,v) and not valid_ordinary(template,v) for v in values):raise ValueError('Invalid socket option slots')
  result[group]=list(values)
 return result
def distribution(item,stone=STONE):
 d=client_data().item(item['template']);capacity(item['template'])
 weapon=d['equip_position']==2
 if item.get('enhancement',0)<0:raise ValueError('Broken equipment requires restoration')
 if stone!=STONE:
  from els_server.domain.ordinary_magic_stones import catalog as ordinary_catalog,distribution as ordinary_distribution
  if str(stone) in ordinary_catalog()['items']:return ordinary_distribution(item,stone)
  from els_server.domain.additional_magic_stones import catalog as additional_catalog,distribution as additional_distribution
  if str(stone) in additional_catalog()['items']:return additional_distribution(item,stone)
  from els_server.domain.atma_sockets import distribution as atma_distribution
  return atma_distribution(item,stone)
 high=bool(d['flags4']&1) or item.get('enhancement',0)>=12
 return catalog()['distributions'][('weapon' if weapon else 'armor')+('-high' if high else '-normal')]
def draw(item,roll,stone=STONE):
 if type(roll) is not int or not 0<=roll<10000:raise ValueError('Socket random range')
 for row in distribution(item,stone):
  if roll<row['weight']:return row['option']
  roll-=row['weight']
 raise ValueError('Socket weight total')
def fee(item,stone=STONE):
 """B308E0: original target base price, occupied slots and material grade."""
 target=client_data().item(item['template']);capacity(item['template'])
 count=max(1,sum(bool(v) for v in item.get('option_groups',{}).get('0',[])))
 base=1000.0 if target['flags4']&1 else struct.unpack_from('<i',target['record'],0x1c)[0]*0.01*count
 grade=(client_data().item(stone)['flags4']>>20)&15
 factor={0:1.,1:2.5,2:2.,3:1.5,4:1.,5:1.,6:3.}.get(grade,0.)
 return int(base*factor)
