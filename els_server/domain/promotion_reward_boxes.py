"""Five official promotion-outfit boxes whose contents come from the client.

The client ships no ItemGroup table for these boxes, so the contents are
derived from the client's own job definitions: every class in ``units``
carries promotion*ItemID (the Lu/main outfit) and, for Lu/Ciel,
m_MinorUnitPromotion*ItemID (the Ciel/minor outfit). A box resolves the job
ancestor at min(character stage, box stage) and grants that ancestor's full
outfit, which is what the official 晋级宝箱 description states. The local
mapping is cross-checked against the human-approved reference mapping for
109999/110850 (all of its groups are reproduced exactly).
"""
import functools,hashlib,json
from types import MappingProxyType
from els_server.paths import PROJECT_ROOT
from els_server.game_data import client_data,CLIENT_SHA

BOXES=frozenset((109999,110850,135666,135867,135871))
POLICY='official-promotion-outfit-boxes-20261101-v1'
RULE='ElWiki 晋级宝箱说明：开启后获得当前职业阶段的晋级时装套装'
AUTHORITY='客户端 units 表每职业的 promotion*ItemID 与 m_MinorUnitPromotion*ItemID 即该职业官方晋级时装集合'
STATEMENT='宝箱按角色职业阶段解析到对应阶的晋级套装；露/希尔同时获得两套（含饰品）'
DERIVATION='按 (family, route, min(角色阶段, 宝箱阶段)) 解析到目标职业，取其 units 定义中的晋级套装'
CROSS_CHECK='references/current-obtainable-consumables-phase-20261028-v1/source/dc80c4007fa65d4be6686c177c5bd75418d53bd4e7c61236501d038eff27130d/promotion_reward_boxes.json 中 109999/110850/135867 全部分组一致'
_MAIN=('promotionWeaponItemID','promotionBodyItemID','promotionLegItemID','promotionHandItemID','promotionFootItemID','promotionAccessoryItemID')
_MINOR=('m_MinorUnitPromotionWeaponItemID','m_MinorUnitPromotionBodyItemID','m_MinorUnitPromotionLegItemID','m_MinorUnitPromotionHandItemID','m_MinorUnitPromotionFootItemID','m_MinorUnitPromotionAccessoryItemID')


def _outfit(unit):
 items=[unit.get(k)or 0 for k in _MAIN]
 if unit.get('unitType')==10:items+=[unit.get(k)or 0 for k in _MINOR]
 return [t for t in items if t]


@functools.lru_cache(maxsize=1)
def catalog():
 path=PROJECT_ROOT/'els_server/data/promotion_reward_boxes.json';raw=path.read_bytes()
 manifest=json.loads(path.with_suffix('.manifest.json').read_text(encoding='utf8'));data=json.loads(raw);client=client_data()
 if (hashlib.sha256(raw).hexdigest()!=manifest['payload_sha256'] or manifest['schema_version']!=1
     or manifest['client_sha256']!=CLIENT_SHA or data['schema_version']!=1 or data['policy']!=POLICY
     or data['client_sha256']!=CLIENT_SHA or data['catalog_sha256']!=client.manifest['catalog_sha256']):
  raise ValueError('Promotion box definition identity')
 rule=data['official_rule'];provenance=data['provenance']
 if (rule['basis'],rule['client_authority'],rule['statement'],rule['original_group_contents_missing'])!=(RULE,AUTHORITY,STATEMENT,True):
  raise ValueError('Promotion box official basis')
 if (provenance['derivation'],provenance['cross_check'],provenance['retail_group_claim'],provenance['client_files_modified'],
     provenance['client_files_added'],provenance['new_game_hooks'],provenance['new_sources'])!=(DERIVATION,CROSS_CHECK,False,0,0,0,0):
  raise ValueError('Promotion box provenance')
 from els_server.domain.inventory_items import FASHION_POSITIONS
 boxes={}
 for row in data['boxes']:
  template=row['template'];item=client.item(template)
  if (template not in BOXES or template in boxes or item['name']!=row['name'] or item['item_type']!=7
      or item['metadata']!=row['metadata'] or item['equip_position']!=0
      or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']):
   raise ValueError('Promotion box original box identity')
  if (row['group'],row['target_stage'],row['min_stage'],row['inventory_days']) not in ((4,None,0,7),(4,1,1,15),(4,2,2,15),(4,3,3,15),(4,1,1,3)):
   raise ValueError('Promotion box local policy')
  if row['min_stage']!=(row['target_stage']or 0):raise ValueError('Promotion box stage gate')
  boxes[template]=MappingProxyType(row)
 if set(boxes)!=set(BOXES):raise ValueError('Promotion box finite scope')
 readers={}
 for row in data['readers']:
  template=row['template'];item=client.item(template)
  if (item['name'],item['metadata'],item['item_type'],item['equip_position'])!=(row['name'],row['metadata'],row['item_type'],row['equip_position']):
   raise ValueError('Promotion outfit item identity')
  if row['group']!=(27 if item['flags8']&256 else 7)or row['max_stack']!=1:raise ValueError('Promotion outfit bag class')
  if row['slot']!=FASHION_POSITIONS[row['equip_position']]:raise ValueError('Promotion outfit wardrobe slot')
  if hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']:raise ValueError('Promotion outfit record identity')
  if template in readers:raise ValueError('Promotion outfit duplicate reader')
  readers[template]=MappingProxyType(row)
 from els_server.domain.equipment_requirements import catalog as requirements
 classes,_=requirements();index={};outfits={}
 if set(classes)!=set(int(k)for k in data['classes'])or len(readers)!=len(data['readers']):
  raise ValueError('Promotion outfit class coverage')
 for key,row in data['classes'].items():
  unit_class=int(key);native=classes[unit_class];unit=client.unit(unit_class)
  if (row['family'],row['route'],row['stage'])!=(native['family'],native['route'],native['stage']):
   raise ValueError('Promotion outfit class stage identity')
  if unit.get('unitType')!=row['family']:raise ValueError('Promotion outfit family identity')
  if sorted(row['items'])!=sorted(_outfit(unit))or len(row['items'])!=len(set(row['items'])):
   raise ValueError('Promotion outfit set identity')
  if not set(row['items'])<=set(readers):raise ValueError('Promotion outfit unregistered set item')
  position=(row['family'],row['route'],row['stage'])
  if position in index:raise ValueError('Promotion outfit duplicate job stage')
  index[position]=unit_class;outfits[unit_class]=MappingProxyType(row)
 for unit_class,row in outfits.items():
  for box in boxes.values():
   stage=row['stage']if box['target_stage']is None else min(row['stage'],box['target_stage'])
   if (row['family'],row['route'],stage)not in index:raise ValueError('Promotion box missing job ancestor')
 return MappingProxyType(dict(sha=manifest['payload_sha256'],boxes=MappingProxyType(boxes),
  readers=tuple(readers[t]for t in sorted(readers)),reader_map=MappingProxyType(readers),
  classes=MappingProxyType(outfits),index=MappingProxyType(index)))


def boxes():return catalog()['boxes']
def readers():return catalog()['readers']
def definition_sha():return catalog()['sha']
def outputs_for(template,unit_class):
 row=boxes().get(template)if type(template)is int else None
 if row is None:raise ValueError('Unknown promotion outfit box')
 classes=catalog()['classes']
 if type(unit_class)is not int or unit_class not in classes:raise ValueError('Promotion box character class')
 current=classes[unit_class]
 if current['stage']<row['min_stage']:raise ValueError('Promotion box requires the matching job advancement')
 stage=current['stage']if row['target_stage']is None else min(current['stage'],row['target_stage'])
 ancestor=catalog()['index'][(current['family'],current['route'],stage)]
 return tuple(dict(template=t,quantity=1)for t in classes[ancestor]['items'])
def preview(template,unit_class):
 row=boxes()[template];outputs=outputs_for(template,unit_class)
 return dict(template=template,name=row['name'],selection_count=0,entries=outputs,promotion_outfit_box=True),outputs
def plan_for(template,unit_class,epoch):
 from els_server.domain.item_expiration import validate
 if type(epoch)is not int or epoch<0:raise ValueError('Promotion box clock')
 row=boxes()[template];deadline=validate(epoch+86400*row['inventory_days']);reader_map=catalog()['reader_map']
 return [dict(template=output['template'],metadata=reader_map[output['template']]['metadata'],
              group=reader_map[output['template']]['group'],quantity=1,expires_at=deadline)for output in outputs_for(template,unit_class)]
