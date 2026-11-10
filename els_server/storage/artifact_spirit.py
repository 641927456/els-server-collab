"""Paid native previews and free Apply: owned, persistent, exactly-once transactions."""
import hashlib,json,secrets,sqlite3
from contextlib import closing
from els_server.storage.profession_state import require_owner
from els_server.domain.local_artifact_rules import draw_spirit,spirit_group,validate_spirit,policy,identity,generation
from els_server.domain.item_expiration import require_current,expired
from els_server.domain.item_locks import require_unlocked,locked
from els_server.protocol.artifact_socket_messages import request,acknowledgement
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_options import replace
from els_server.storage.artifact_progression import consume
from els_server.storage.npc_trade import balances,charge

def signature(item):
 # Moving the UID does not reroll or invalidate a paid preview; Apply still
 # requires its owner, an unequipped target and unchanged native option state.
 return hashlib.sha256(json.dumps({k:v for k,v in item.items() if k not in ('group','slot','lock_until')},sort_keys=True).encode()).hexdigest()

def perform(path,owner,payload,operation,randbelow=secrets.randbelow,encode=acknowledgement,*,account_id=None):
 uid,groups,profession,mode=request(payload)
 if profession or mode not in (7,8,9,10,13):raise ValueError('Unsupported spirit operation')
 owner,digest=_identity(owner,0x6e7,payload,operation)
 with closing(sqlite3.connect(path,timeout=10)) as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
  if account_id is not None:require_owner(db,owner,account_id)
  old=_previous(db,operation,digest);before=load_items(db,owner);ed=balances(db,owner)['ed']
  item=next((i for i in before if i['uid']==uid),None)
  db.execute('CREATE TABLE IF NOT EXISTS artifact_spirit_previews (item_uid INTEGER PRIMARY KEY,owner INTEGER NOT NULL,option_id INTEGER NOT NULL,expected_sha256 TEXT NOT NULL,mode INTEGER NOT NULL,policy_json TEXT NOT NULL)')
  pending=db.execute('SELECT option_id,expected_sha256,mode FROM artifact_spirit_previews WHERE item_uid=? AND owner=?',(uid,owner)).fetchone()
  if old is not None:
   current={(i['group'],i['slot']):i for i in before};option=pending[0] if pending else next(iter(item.get('option_groups',{}).get(str(spirit_group(item['template'])),[])),0) if item else 0
   return [encode(uid,ed,current_changes(db,operation,owner,0x6e7,old,before),mode=mode,option=option)]
  if item is None or item['group']!=1 or item['count']!=1 or item.get('identified') is False or not item.get('artifact_socket_open'):raise ValueError('Owned identified unequipped open-slot Artifact required')
  require_current(item);require_unlocked(item);category=spirit_group(item['template'])
  from els_server.domain.artifact_progression import catalog
  if item['template'] not in catalog()['equipment']:raise ValueError('Spirit targets must be actual wearable Artifacts')
  if set(groups)!={category} or set(groups[category])!={0}:raise ValueError('Original spirit category/slot required')
  value=groups[category][0];previous=item.get('option_groups',{});positions=[(item['group'],item['slot'])]
  if mode in (8,10):
   if pending is None or pending[0]!=value or pending[1]!=signature(item) or pending[2]!=(7 if mode==8 else 9):raise ValueError('Missing, stale or forged spirit preview')
   option=pending[0];replace(db,owner,uid,previous,{**previous,str(category):[option]})
   db.execute('DELETE FROM artifact_spirit_previews WHERE item_uid=? AND owner=?',(uid,owner))
  else:
   material=next((i for i in before if i['uid']==value),None)
   if material is None:raise ValueError('Owned spirit material required')
   require_current(material);require_unlocked(material)
   if ed<policy()['generation']['preview_ed']:raise ValueError('Insufficient spirit preview ED')
   if mode==7:
    if material['group']!=3 or material['template']!=118206:raise ValueError('Original spirit fragments required')
    needed=policy()['generation']['preview_fragments']
    # Native stacks may be split; the selected UID anchors the material type.
    stacks=sorted((i for i in before if i['group']==3 and i['template']==118206 and not expired(i) and not locked(i)),key=lambda i:(i['uid']!=value,i['slot']))
    if sum(i['count'] for i in stacks)<needed:raise ValueError('Insufficient spirit fragments')
    option=draw_spirit(item['template'],randbelow=randbelow)
   else:
    if material['group']!=1:raise ValueError('Original selected-family shard required')
    if str(material['template']) in generation()['generated']:
     if spirit_group(material['template'])!=category:raise ValueError('Generated spirit part mismatch')
     values=validate_spirit(material['template'],material.get('option_groups',{}).get(str(category),[]))
     if len(values)!=1:raise ValueError('Generated spirit effect missing')
     option=values[0]
    else:option=draw_spirit(item['template'],material['template'],randbelow)
    needed=1;stacks=[material]
   ed=charge(db,owner,balances(db,owner),policy()['generation']['preview_ed'])
   for stack in stacks:
    amount=min(needed,stack['count']);positions.append(consume_material(db,owner,stack,amount));needed-=amount
    if not needed:break
   if mode==13:
    replace(db,owner,uid,previous,{**previous,str(category):[option]})
    db.execute('DELETE FROM artifact_spirit_previews WHERE item_uid=? AND owner=?',(uid,owner))
   else:
    db.execute('INSERT INTO artifact_spirit_previews VALUES (?,?,?,?,?,?) ON CONFLICT(item_uid) DO UPDATE SET owner=excluded.owner,option_id=excluded.option_id,expected_sha256=excluded.expected_sha256,mode=excluded.mode,policy_json=excluded.policy_json',(uid,owner,option,signature(item),mode,json.dumps(identity(),sort_keys=True)))
  validate_spirit(item['template'],[option]);after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
  result=[encode(uid,ed,[(p,current.get(p)) for p in positions],mode=mode,option=option,options=[option])]
  _commit(db,operation,digest,owner,0x6e7,positions,before,after)
  return result

def consume_material(db,owner,item,count):
 if item['group']==4:return consume(db,owner,item,count)[0]
 if item['group']==3 and item['template']==118206 and type(count) is int and 1<=count<=item['count']:
  from els_server.storage.item_instances import remove
  if count==item['count']:remove(db,owner,item)
  elif db.execute('UPDATE inventory_items SET count=count-? WHERE owner=? AND uid=?',(count,owner,item['uid'])).rowcount!=1:raise ValueError('Fragment owner mismatch')
  return item['group'],item['slot']
 if count!=1 or item['count']!=1:raise ValueError('Single selected spirit shard required')
 from els_server.storage.item_instances import remove
 remove(db,owner,item);return item['group'],item['slot']
