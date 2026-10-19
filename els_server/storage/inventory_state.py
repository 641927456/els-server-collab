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
 inventory_payload(items)  # Verify persisted identities/positions and wire before use.
 from els_server.storage.bag_capacity import allowances
 limits=allowances(db,owner)
 if any(i['group'] not in (9,24) and i['slot']>=limits[i['group']] for i in items):raise ValueError('Item exceeds owned bag capacity')
 return items
def validate_plan(plan):
 if not isinstance(plan,list) or not 1<=len(plan)<=36:raise ValueError('Inventory grant plan bound')
 for p in plan:
  if not isinstance(p,dict) or set(p)-{'expires_at','enhancement'}!={'template','metadata','quantity','group'} or any(type(v) is not int for v in p.values()):raise ValueError('Invalid inventory grant plan')
  from els_server.domain.acquisition_policy import require_acquirable
  require_acquirable(p['template'])
  if 'enhancement' in p:
   from els_server.domain.equipment_enhancement import validate as validate_enhancement
   validate_enhancement(p['template'],p['enhancement'])
  if 'expires_at' in p:
   from els_server.domain.item_expiration import validate as validate_expiration
   validate_expiration(p['expires_at'])
  from els_server.domain.repair_pass import TEMPLATE as REPAIR_PASS
  if p['template']==REPAIR_PASS and ('expires_at' not in p or p['quantity']!=1):raise ValueError('Repair pass grant requires one explicitly timed instance')
  if p['template'] not in VERIFIED_TEMPLATES or p['metadata']!=VERIFIED_TEMPLATES[p['template']] or p['group']!=TEMPLATE_BAG_GROUPS[p['template']] or not 1<=p['quantity']<=LOCAL_MAX_STACK:raise ValueError('Unverified inventory grant template/count')
 return [dict(p) for p in plan]
def grant_items(db,plan,owner=1001,*,chip_options=None):
 owner=character_uid(owner)
 plan=validate_plan(plan);items=load_items(db,owner);changed={}
 from els_server.domain.equipment_chip_rules import TEMPLATE as CHIP,generate as chip_generate,source_options as chip_source
 approved_chip=None
 if chip_options is not None:
  if len(plan)!=1 or plan[0]['template']!=CHIP or plan[0]['quantity']!=1 or not isinstance(chip_options,dict) or set(chip_options)!={'1'}:raise ValueError('Chip issued options require one finite server chip plan')
  approved_chip={'1':chip_source(chip_options['1'])}
 from els_server.storage.bag_capacity import allowances
 limits=allowances(db,owner)
 for p in plan:
  remaining=p['quantity']
  for i in items:
   if (i['template'],i['metadata'],i['group'])==(p['template'],p['metadata'],p['group']) and i.get('expires_at')==p.get('expires_at') and TEMPLATE_MAX_STACKS[i['template']]>1 and i['count']<TEMPLATE_MAX_STACKS[i['template']]:
    delta=min(remaining,TEMPLATE_MAX_STACKS[i['template']]-i['count']);i['count']+=delta;remaining-=delta
    db.execute('UPDATE inventory_items SET count=? WHERE uid=? AND owner=?',(i['count'],i['uid'],owner));changed[i['uid']]=dict(i)
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
   validate_item(i)
   db.execute('UPDATE inventory_sequence SET next_uid=? WHERE id=1',(uid+1,))
   db.execute('INSERT INTO inventory_items VALUES (?,?,?,?,?,?,?)',(uid,owner,i['template'],i['metadata'],i['count'],i['group'],slot))
   if i['template']==CHIP:
    from els_server.storage.equipment_options import replace as replace_chip_options
    replace_chip_options(db,owner,uid,{},i['option_groups'])
   if 'expires_at' in i:
    from els_server.storage.item_expiration import assign
    assign(db,owner,uid,i['expires_at'])
   from els_server.domain.normal_equipment import definitions as normal_equipment_definitions
   if i['template'] in normal_equipment_definitions():
    from els_server.domain.equipment_durability import maximum
    from els_server.storage.equipment_durability import replace_durability
    i['durability']=replace_durability(db,owner,uid,0,maximum(i['template']))
   if i.get('enhancement'):
    from els_server.storage.equipment_enhancement import replace as replace_enhancement
    replace_enhancement(db,owner,uid,0,i['enhancement'])
   from els_server.storage.artifact_generation import initialize
   initialize(db,owner,i)
   items.append(i);changed[uid]=dict(i);remaining-=i['count']
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
