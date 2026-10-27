"""Local inventory allocation/stacking, sharing the reward SQL transaction."""
import json,sqlite3
from contextlib import closing
from pathlib import Path
from els_server.storage.character_schema import character_uid,migrate_character_schema
from els_server.domain.inventory_items import LOCAL_BAG_CAPACITY,LOCAL_MAX_STACK,VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS,validate_item,inventory_payload
from els_server.storage.reward_state import validate_balances
class InventoryFull(ValueError):pass
def ensure_inventory(db):
 migrate_character_schema(db)
 db.execute('CREATE TABLE IF NOT EXISTS inventory_items (uid INTEGER PRIMARY KEY CHECK(uid>0), owner INTEGER NOT NULL CHECK(owner>=1001), template INTEGER NOT NULL, metadata INTEGER NOT NULL, count INTEGER NOT NULL CHECK(count>0), bag_group INTEGER NOT NULL, slot INTEGER NOT NULL, UNIQUE(owner,bag_group,slot))')
 db.execute('CREATE TABLE IF NOT EXISTS inventory_sequence (id INTEGER PRIMARY KEY CHECK(id=1), next_uid INTEGER NOT NULL CHECK(next_uid>0))')
 db.execute('INSERT OR IGNORE INTO inventory_sequence VALUES (1,1001001)')
 db.execute('CREATE TABLE IF NOT EXISTS reward_inventory_receipts (run_id TEXT PRIMARY KEY REFERENCES reward_receipts(run_id), items_json TEXT NOT NULL)')
 db.execute('CREATE TABLE IF NOT EXISTS inventory_migrations (name TEXT PRIMARY KEY, audit_json TEXT NOT NULL)')
 from els_server.storage.equipment_attributes import ensure_attributes
 ensure_attributes(db)

def normalize_legacy_potion_groups(items):
 # Historical receipts remain immutable; only the known erroneous classification
 # is normalized when comparing/replaying after the audited save migration.
 return [{**i,'group':6} if i.get('template')==77000 and i.get('metadata')==2 and i.get('group')==2 else
         {**i,'group':27} if i.get('group')==7 and TEMPLATE_BAG_GROUPS.get(i.get('template'))==27 else dict(i) for i in items]

def migrate_fashion_bag(db):
 name='ice-heater-fashion-native-bag-27-v1'
 if db.execute('SELECT 1 FROM inventory_migrations WHERE name=?',(name,)).fetchone():return
 rows=[dict(zip(('uid','template','metadata','count','group','slot'),r)) for r in db.execute('SELECT uid,template,metadata,count,bag_group,slot FROM inventory_items WHERE owner=1001 ORDER BY uid')]
 occupied={i['slot'] for i in rows if i['group']==27};changes=[]
 for old in rows:
  if old['group']!=7 or TEMPLATE_BAG_GROUPS.get(old['template'])!=27:continue
  slot=old['slot'] if old['slot'] not in occupied else next((n for n in range(LOCAL_BAG_CAPACITY) if n not in occupied),None)
  if slot is None:raise InventoryFull('Fashion classification migration requires a free slot')
  new={**old,'group':27,'slot':slot};validate_item(new);occupied.add(slot)
  db.execute('UPDATE inventory_items SET bag_group=27,slot=? WHERE owner=1001 AND uid=?',(slot,old['uid']));changes.append({'before':old,'after':new})
 if changes:db.execute('INSERT INTO inventory_migrations VALUES (?,?)',(name,json.dumps({'changes':changes,'receipts_preserved':True},sort_keys=True)))

def migrate_potion_bag(db):
 name='potion-77000-accessory-to-quick-slot-v1'
 if db.execute('SELECT 1 FROM inventory_migrations WHERE name=?',(name,)).fetchone():return
 rows=[dict(zip(('uid','template','metadata','count','group','slot'),r)) for r in db.execute('SELECT uid,template,metadata,count,bag_group,slot FROM inventory_items WHERE owner=1001 ORDER BY uid')]
 occupied={i['slot'] for i in rows if i['group']==6};changes=[]
 for old in rows:
  if (old['template'],old['metadata'],old['group'])!=(77000,2,2):continue
  slot=old['slot'] if old['slot'] not in occupied else next((n for n in range(LOCAL_BAG_CAPACITY) if n not in occupied),None)
  if slot is None:raise InventoryFull('Potion classification migration requires a free potion slot')
  new={**old,'group':6,'slot':slot};validate_item(new);occupied.add(slot)
  db.execute('UPDATE inventory_items SET bag_group=6,slot=? WHERE owner=1001 AND uid=?',(slot,old['uid']))
  changes.append({'before':old,'after':new})
 load_items(db)
 db.execute('INSERT INTO inventory_migrations VALUES (?,?)',(name,json.dumps({'changes':changes,'receipts_preserved':True},sort_keys=True)))
def load_items(db,owner=1001):
 owner=character_uid(owner)
 items=[dict(zip(('uid','template','metadata','count','group','slot'),r)) for r in db.execute('SELECT uid,template,metadata,count,bag_group,slot FROM inventory_items WHERE owner=? ORDER BY bag_group,slot',(owner,))]
 from els_server.storage.equipment_attributes import attach_attributes
 attach_attributes(db,items,owner)
 from els_server.storage.equipment_durability import attach_durability
 attach_durability(db,items,owner)
 from els_server.storage.equipment_enhancement import attach as attach_enhancement
 attach_enhancement(db,items,owner)
 from els_server.storage.enhancement_progress import attach as attach_progress
 attach_progress(db,items,owner)
 from els_server.storage.item_expiration import attach as attach_expiration
 attach_expiration(db,items,owner)
 from els_server.storage.item_locks import attach as attach_locks
 attach_locks(db,items,owner)
 from els_server.storage.equipment_options import attach as attach_options
 attach_options(db,items,owner)
 from els_server.storage.equipment_identification import attach as attach_identification
 attach_identification(db,items,owner)
 from els_server.storage.item_seals import attach as attach_seals
 attach_seals(db,items,owner)
 from els_server.storage.artifact_equipment_state import attach as attach_artifact_equipment
 attach_artifact_equipment(db,items,owner)
 from els_server.storage.equipment_chip import attach as attach_chip
 attach_chip(db,items,owner)
 from els_server.storage.equipment_reforge import attach as attach_reforge
 attach_reforge(db,items,owner)
 from els_server.storage.wardrobe import attach as attach_wardrobe
 attach_wardrobe(db,items,owner)
 from els_server.domain.cartridge_registration_rules import project as project_cartridge
 project_cartridge(db,items,owner)
 from els_server.domain.cartridge_selection_box import BOX as read_box,read_existing_box
 for index,item in enumerate(items):
  if item["template"]==read_box:
   items[index]=read_existing_box(item)
 from els_server.domain.wardrobe_ticket_box import BOX as wardrobe_box,read_existing_box as read_wardrobe_box
 for index,item in enumerate(items):
  if item["template"]==wardrobe_box:
   items[index]=read_wardrobe_box(item)
 from els_server.domain.erp_potions_existing import TEMPLATES as erp_potions,read_existing as read_erp_potion
 for index,item in enumerate(items):
  if item['template']in erp_potions:
   items[index]=read_erp_potion(item)
 from els_server.domain.teacher_elixir_boxes import BOXES as teacher_boxes,read_existing as read_teacher_box
 for index,item in enumerate(items):
  if item['template']in teacher_boxes:items[index]=read_teacher_box(item)
 from els_server.domain.life_potions_existing import TEMPLATES as life_potions,read_existing as read_life_potion
 for index,item in enumerate(items):
  if item['template']in life_potions:items[index]=read_life_potion(item)
 from els_server.domain.wisdom_potions import TEMPLATES as wisdom_potions,read_existing as read_wisdom_potion
 for index,item in enumerate(items):
  if item['template']in wisdom_potions:items[index]=read_wisdom_potion(item)
 from els_server.domain.normal_fatigue_rules import read_existing as read_normal_fatigue
 for index,item in enumerate(items):
  if item["template"]in (77200, 77201, 154118, 166610, 168348, 189209, 190393, 190398, 297093, 297761, 710096, 710097, 710098, 710099, 710100, 710101, 710102, 710103, 110004219):items[index]=read_normal_fatigue(item)
 inventory_payload(items)  # Verify persisted identities/positions and wire before use.
 from els_server.storage.bag_capacity import allowances
 limits=allowances(db,owner)
 if any(i['group'] not in (9,22,23,24) and i['slot']>=limits[i['group']] for i in items):raise ValueError('Item exceeds owned bag capacity')
 return items
def validate_plan(plan,*,selected_accessory_box=None,cartridge_box_source=None,cartridge_select_source=None,cartridge_recipe679_source=None,fish_erp_source=None,raid_reward_source=None,silver_source=None,daily_special_source=None,regional_cube_source=None):
 if regional_cube_source is not None:
  if any(v is not None for v in(selected_accessory_box,cartridge_box_source,cartridge_select_source,cartridge_recipe679_source,fish_erp_source,raid_reward_source,silver_source,daily_special_source)):
   raise ValueError('Incompatible regional cube inventory sources')
  from els_server.storage.regional_boss_cube_source import validate_source as _regional_source
  _regional_source(regional_cube_source).validate_plan(plan)
 if daily_special_source is not None:
  if any(v is not None for v in(selected_accessory_box,cartridge_box_source,cartridge_select_source,cartridge_recipe679_source,fish_erp_source,raid_reward_source,silver_source)):raise ValueError('Incompatible daily inventory sources')
  from els_server.storage.ariel_daily_special import validate_source as _daily_source
  _daily_source(daily_special_source).validate_plan(plan)
 if raid_reward_source is not None:
  if any(v is not None for v in(selected_accessory_box,cartridge_box_source,cartridge_select_source,cartridge_recipe679_source,fish_erp_source)):raise ValueError('Incompatible raid inventory sources')
  from els_server.domain.raid_reward_items import validate_source as _raid_source
  _raid_source(raid_reward_source).validate_plan(plan)
 if fish_erp_source is not None:
  if any(x is not None for x in(selected_accessory_box,cartridge_box_source,cartridge_select_source,cartridge_recipe679_source)):raise ValueError('Incompatible fish ERP grant source')
  from els_server.domain.fish_exchange_erp import validate_source as validate_fish_erp_source
  validate_fish_erp_source(fish_erp_source).validate_plan(plan)
 if cartridge_recipe679_source is not None:
  if cartridge_box_source is not None or cartridge_select_source is not None or selected_accessory_box is not None:raise ValueError("Incompatible inventory grant sources")
  from els_server.domain.cartridge_recipe679_rules import validate_recipe_source
  validate_recipe_source(cartridge_recipe679_source).validate_plan(plan)
 if cartridge_select_source is not None:
  if cartridge_box_source is not None or selected_accessory_box is not None:raise ValueError("Incompatible inventory grant sources")
  from els_server.domain.cartridge_exchange_rules import validate_select_source
  validate_select_source(cartridge_select_source).validate_plan(plan)
 if cartridge_box_source is not None:
  if selected_accessory_box is not None:raise ValueError("Incompatible inventory grant sources")
  from els_server.domain.cartridge_selection_box import validate_source
  validate_source(cartridge_box_source).validate_plan(plan)
 if not isinstance(plan,list) or not 1<=len(plan)<=36:raise ValueError('Inventory grant plan bound')
 if selected_accessory_box is not None:
  from els_server.domain.boosting_2026_accessories import validate_box_grants
  validate_box_grants(selected_accessory_box,plan)
 for p in plan:
  if not isinstance(p,dict) or set(p)-{'expires_at','enhancement'}!={'template','metadata','quantity','group'} or any(type(v) is not int for v in p.values()):raise ValueError('Invalid inventory grant plan')
  from els_server.domain.acquisition_policy import require_acquirable
  if selected_accessory_box is None:require_acquirable(p['template'],cartridge_box_source=cartridge_box_source,cartridge_select_source=cartridge_select_source,cartridge_recipe679_source=cartridge_recipe679_source,raid_reward_source=raid_reward_source,silver_source=silver_source,daily_special_source=daily_special_source,regional_cube_source=regional_cube_source)
  if 'enhancement' in p:
   from els_server.domain.equipment_enhancement import validate as validate_enhancement
   validate_enhancement(p['template'],p['enhancement'])
  if 'expires_at' in p:
   from els_server.domain.item_expiration import validate as validate_expiration
   validate_expiration(p['expires_at'])
  from els_server.domain.repair_pass import TEMPLATE as REPAIR_PASS
  if p['template']==REPAIR_PASS and ('expires_at' not in p or p['quantity']!=1):raise ValueError('Repair pass grant requires one explicitly timed instance')
  if cartridge_recipe679_source is not None:
   if p!=dict(template=119335,metadata=0,group=4,quantity=1):raise ValueError('Recipe679 private singleton plan')
  elif p['template'] not in VERIFIED_TEMPLATES or p['metadata']!=VERIFIED_TEMPLATES[p['template']] or p['group']!=TEMPLATE_BAG_GROUPS[p['template']] or not 1<=p['quantity']<=LOCAL_MAX_STACK:raise ValueError('Unverified inventory grant template/count')
 return [dict(p) for p in plan]
def grant_items(db,plan,owner=1001,*,chip_options=None,selected_accessory_box=None,cartridge_box_source=None,cartridge_select_source=None,cartridge_recipe679_source=None,fish_erp_source=None,raid_reward_source=None,silver_source=None,daily_special_source=None,regional_cube_source=None):
 if regional_cube_source is not None:
  if any(v is not None for v in(chip_options,selected_accessory_box,cartridge_box_source,cartridge_select_source,cartridge_recipe679_source,fish_erp_source,raid_reward_source,silver_source,daily_special_source)):
   raise ValueError('Incompatible regional cube inventory sources')
  from els_server.storage.regional_boss_cube_source import validate_source as _regional_source
  _regional_source(regional_cube_source).bind_factory(db,owner,plan)
 if daily_special_source is not None:
  if any(v is not None for v in(chip_options,selected_accessory_box,cartridge_box_source,cartridge_select_source,cartridge_recipe679_source,fish_erp_source,raid_reward_source,silver_source)):raise ValueError('Incompatible daily inventory sources')
  from els_server.storage.ariel_daily_special import validate_source as _daily_source
  _daily_source(daily_special_source).bind_factory(db,owner,plan)
 if raid_reward_source is not None:
  if any(v is not None for v in(selected_accessory_box,cartridge_box_source,cartridge_select_source,cartridge_recipe679_source,fish_erp_source)):raise ValueError('Incompatible raid inventory sources')
  from els_server.domain.raid_reward_items import validate_source as _raid_source
  _raid_source(raid_reward_source).bind_factory(db,owner,plan)
 owner=character_uid(owner)
 if fish_erp_source is not None:
  if any(x is not None for x in(chip_options,selected_accessory_box,cartridge_box_source,cartridge_select_source,cartridge_recipe679_source)):raise ValueError('Incompatible fish ERP factory source')
  from els_server.domain.fish_exchange_erp import validate_source as validate_fish_erp_source
  validate_fish_erp_source(fish_erp_source).bind_factory(db,owner,plan)
 if cartridge_recipe679_source is not None:
  if cartridge_box_source is not None or cartridge_select_source is not None or selected_accessory_box is not None or chip_options is not None:raise ValueError("Incompatible inventory grant sources")
  from els_server.domain.cartridge_recipe679_rules import validate_recipe_source
  validate_recipe_source(cartridge_recipe679_source).bind_factory(db,owner,plan)
 if cartridge_select_source is not None:
  if cartridge_box_source is not None or selected_accessory_box is not None or chip_options is not None:raise ValueError("Incompatible inventory grant sources")
  from els_server.domain.cartridge_exchange_rules import validate_select_source
  validate_select_source(cartridge_select_source).bind_factory(db,owner,plan)
 if cartridge_box_source is not None:
  if selected_accessory_box is not None or chip_options is not None:raise ValueError("Incompatible inventory grant sources")
  from els_server.domain.cartridge_selection_box import validate_source
  validate_source(cartridge_box_source).bind_factory(db,owner,plan)
 if silver_source is not None:
  if any(v is not None for v in(chip_options,selected_accessory_box,cartridge_box_source,cartridge_select_source,cartridge_recipe679_source,fish_erp_source,raid_reward_source,daily_special_source)):raise ValueError('Incompatible Mirror inventory sources')
  from els_server.domain.silver_mirror_rewards import validate_source as validate_mirror_source
  validate_mirror_source(silver_source).bind_factory(db,owner,plan)
 plan=validate_plan(plan,selected_accessory_box=selected_accessory_box,cartridge_box_source=cartridge_box_source,cartridge_select_source=cartridge_select_source,cartridge_recipe679_source=cartridge_recipe679_source,fish_erp_source=fish_erp_source,raid_reward_source=raid_reward_source,silver_source=silver_source,daily_special_source=daily_special_source,regional_cube_source=regional_cube_source);items=load_items(db,owner);changed={}
 from els_server.domain.equipment_chip_rules import TEMPLATE as CHIP,generate as chip_generate,source_options as chip_source
 approved_chip=None
 if chip_options is not None:
  if len(plan)!=1 or plan[0]['template']!=CHIP or plan[0]['quantity']!=1 or not isinstance(chip_options,dict) or set(chip_options)!={'1'}:raise ValueError('Chip issued options require one finite server chip plan')
  approved_chip={'1':chip_source(chip_options['1'])}
 from els_server.storage.bag_capacity import allowances
 limits=allowances(db,owner)
 for p in plan:
  remaining=p['quantity']
  for index,i in enumerate(items):
   if (i['template'],i['metadata'],i['group'])==(p['template'],p['metadata'],p['group']) and i.get('expires_at')==p.get('expires_at') and TEMPLATE_MAX_STACKS[i['template']]>1 and i['count']<TEMPLATE_MAX_STACKS[i['template']] and (fish_erp_source is None or fish_erp_source.can_stack(i,p)):
    delta=min(remaining,TEMPLATE_MAX_STACKS[i['template']]-i['count']);i['count']+=delta;remaining-=delta
    db.execute('UPDATE inventory_items SET count=? WHERE uid=? AND owner=?',(i['count'],i['uid'],owner))
    if fish_erp_source is not None:i=fish_erp_source.admit_instance(dict(i));items[index]=i
    changed[i['uid']]=i if fish_erp_source is not None else dict(i)
    if not remaining:break
  while remaining:
   occupied={i['slot'] for i in items if i['group']==p['group']};slot=next((n for n in range(limits[p['group']]) if n not in occupied),None)
   if slot is None:raise InventoryFull('Local inventory is full')
   uid=db.execute('SELECT next_uid FROM inventory_sequence WHERE id=1').fetchone()[0]
   if type(uid) is not int or not 1<=uid<2**63-1:raise ValueError('Inventory UID sequence bound')
   i={'uid':uid,'template':p['template'],'metadata':p['metadata'],'group':p['group'],'slot':slot,'count':min(remaining,TEMPLATE_MAX_STACKS[p['template']])}
   if 'expires_at' in p:i['expires_at']=p['expires_at']
   if p.get('enhancement'):i['enhancement']=p['enhancement']
   if i['template']==CHIP:i['option_groups']={'1':list(approved_chip['1'])} if approved_chip is not None else chip_generate()
   from els_server.domain.equipment_circuit_rules import material as circuit_material,generate as circuit_generate
   typed_circuit=raid_reward_source is not None and circuit_material(i['template'])is not None
   if typed_circuit:i['option_groups']=circuit_generate(i['template'])
   if cartridge_recipe679_source is not None:i=validate_recipe_source(cartridge_recipe679_source).admit_instance(i)
   if fish_erp_source is not None:i=fish_erp_source.admit_instance(i)
   if silver_source is not None and silver_source.options is not None:i['option_groups']=dict(silver_source.options)
   validate_item(i)
   db.execute('UPDATE inventory_sequence SET next_uid=? WHERE id=1',(uid+1,))
   db.execute('INSERT INTO inventory_items VALUES (?,?,?,?,?,?,?)',(uid,owner,i['template'],i['metadata'],i['count'],i['group'],slot))
   if silver_source is not None and silver_source.options is not None:
    from els_server.storage.equipment_options import replace as replace_mirror_options
    replace_mirror_options(db,owner,uid,{},i['option_groups'])
   if i['template']==CHIP or typed_circuit:
    from els_server.storage.equipment_options import replace as replace_chip_options
    replace_chip_options(db,owner,uid,{},i['option_groups'])
   if 'expires_at' in i:
    from els_server.storage.item_expiration import assign
    assign(db,owner,uid,i['expires_at'])
   from els_server.domain.normal_equipment import definitions as normal_equipment_definitions
   if i['template'] in normal_equipment_definitions() or i['template'] in (135928,135929,135931):
    from els_server.domain.equipment_durability import maximum
    from els_server.storage.equipment_durability import replace_durability
    i['durability']=replace_durability(db,owner,uid,0,maximum(i['template']))
   if i.get('enhancement'):
    from els_server.storage.equipment_enhancement import replace as replace_enhancement
    replace_enhancement(db,owner,uid,0,i['enhancement'])
   from els_server.storage.artifact_generation import initialize
   initialize(db,owner,i)
   items.append(i);changed[uid]=i if fish_erp_source is not None else dict(i);remaining-=i['count']
 if regional_cube_source is not None:regional_cube_source.verify_after()
 if fish_erp_source is not None:fish_erp_source.verify_after()
 inventory_payload(items)
 return list(changed.values())
class InventoryState:
 def __init__(self,path,uid=1001):
  self.uid=character_uid(uid)
  self.path=Path(path)
  with closing(sqlite3.connect(self.path,timeout=10)) as db,db:
   db.execute('BEGIN IMMEDIATE');ensure_inventory(db);migrate_fashion_bag(db);migrate_potion_bag(db)
 def snapshot(self):
  with closing(sqlite3.connect(self.path,timeout=10)) as db:
   db.execute('BEGIN')
   balances=validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(self.uid,)).fetchone());items=load_items(db,self.uid);db.commit()
  return {'balances':balances,'items':items}
