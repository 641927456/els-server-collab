"""Atomic local ED/experience receipts. Protocol integration needs verified fields."""
import hashlib,json,sqlite3,uuid
from contextlib import closing
from pathlib import Path
from els_server.storage.character_schema import character_uid,migrate_character_schema

class RewardConflict(ValueError):pass
def validate_balances(row):
 if row is None or len(row)!=3 or any(type(v) is not int or not 0<=v<=2**63-1 for v in row):raise ValueError('Invalid persisted reward balances')
 return dict(zip(('ed','experience','revision'),row))
class RewardState:
 def __init__(self,path,uid=1001,*,account_id=None):
  self.uid=character_uid(uid)
  self.account_id=account_id
  self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
  with closing(self._connect()) as db,db:
   db.execute('BEGIN IMMEDIATE');migrate_character_schema(db)
   db.execute('CREATE TABLE IF NOT EXISTS reward_balances (uid INTEGER PRIMARY KEY CHECK(uid>=1001), ed INTEGER NOT NULL CHECK(ed>=0), experience INTEGER NOT NULL CHECK(experience>=0), revision INTEGER NOT NULL CHECK(revision>=0))')
   db.execute('INSERT OR IGNORE INTO reward_balances VALUES (?,0,0,0)',(self.uid,))
   db.execute('CREATE TABLE IF NOT EXISTS reward_receipts (run_id TEXT PRIMARY KEY, proof_sha256 TEXT NOT NULL, grant_json TEXT NOT NULL, response BLOB NOT NULL, balance_json TEXT NOT NULL)')
   db.execute('CREATE TABLE IF NOT EXISTS reward_title_receipts (run_id TEXT PRIMARY KEY REFERENCES reward_receipts(run_id), owner INTEGER NOT NULL, effect_json TEXT NOT NULL)')
   db.execute('CREATE TABLE IF NOT EXISTS dungeon_records (uid INTEGER NOT NULL, map_id INTEGER NOT NULL, seconds INTEGER NOT NULL CHECK(seconds>0 AND seconds<=2147483647), PRIMARY KEY(uid,map_id))')
 def _connect(self):return sqlite3.connect(self.path,timeout=10)
 def balances(self):
  db=self._connect()
  try:r=db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(self.uid,)).fetchone()
  finally:db.close()
  return validate_balances(r)
 def grant(self,run_id,proof,ed,experience,response_builder=None,item_plan=None,inventory_response_builder=None,*,dungeon_clear=None,challenge_clear=None,transaction=None,clear_assessment=None,artifact_base=None,title_economy=None,title_dungeon=None,attendance_clear=None,experience_limit=None,resonance_source=None):
  # A run UUID is allocated by the authenticated server, never by a client.
  if not isinstance(run_id,str) or str(uuid.UUID(run_id))!=run_id:raise ValueError('Noncanonical reward run UUID')
  if not isinstance(proof,bytes) or not proof or len(proof)>8192:raise ValueError('Reward evidence bound')
  if any(type(n) is not int or not 0<=n<=2**63-1 for n in (ed,experience)):raise ValueError('Reward amount bound')
  if inventory_response_builder is not None:
   if response_builder is not None or item_plan is None or not callable(inventory_response_builder):raise ValueError('Inventory response requires one builder and an item plan')
  elif not callable(response_builder):raise ValueError('Reward response builder required')
  grant={'ed':ed,'experience':experience}
  if resonance_source is not None:
   if resonance_source not in ('kill','clear') or (resonance_source=='clear')!=(dungeon_clear is not None):raise ValueError('ERP source boundary')
   grant['resonance_source']=resonance_source
   from els_server.domain.resonance import experience_multiplier
   grant['resonance_multiplier']=experience_multiplier()
  if experience_limit is not None:
   if type(experience_limit) is not int or not 0<=experience_limit<=2**31-1:raise ValueError('Experience limit bound')
   grant['experience_limit']=experience_limit
  if title_dungeon is not None and (title_economy!='ground_ed' or type(title_dungeon) is not int or not 1<=title_dungeon<=2**31-1):raise ValueError('Title coin requires an issued dungeon identity')
  if title_economy is not None:
   if title_economy not in ('clear','ground_ed') or inventory_response_builder is not None:raise ValueError('Invalid title economy source')
   if title_economy=='clear' and dungeon_clear is None:raise ValueError('Title EXP requires dungeon clear')
   if title_economy=='ground_ed' and (dungeon_clear is not None or item_plan is not None or experience or challenge_clear is not None or clear_assessment is not None):raise ValueError('Title coin source cannot grant other rewards')
   if title_economy=='ground_ed' and title_dungeon is None:raise ValueError('Missing issued title coin dungeon')
   grant['title_economy']=title_economy
   if title_dungeon is not None:grant['title_dungeon']=title_dungeon
  if clear_assessment is not None:
   from els_server.storage.local_clear_rules import validate_assessment
   clear_assessment=validate_assessment(clear_assessment)
   if dungeon_clear is None or clear_assessment['dungeon']!=dungeon_clear[0] or clear_assessment['seconds']!=dungeon_clear[1] or type(artifact_base) is not int or not 0<=artifact_base<=2**31-1:raise ValueError('Assessment requires matching committed clear and explicit base EXP')
   grant['local_assessment']=clear_assessment;grant['artifact_base']=artifact_base
  elif artifact_base is not None:raise ValueError('Artifact base EXP requires an authoritative clear')
  if challenge_clear is not None:
   if (not isinstance(challenge_clear,dict) or set(challenge_clear)!={'attempt','dungeon','now'}
       or str(uuid.UUID(challenge_clear['attempt']))!=challenge_clear['attempt']
       or any(type(challenge_clear[k]) is not int or challenge_clear[k]<0 for k in ('dungeon','now'))):raise ValueError('Invalid challenge clear effect')
   grant['challenge_clear']=dict(challenge_clear)
  if dungeon_clear is not None:
   if (type(dungeon_clear) is not tuple or len(dungeon_clear)!=2 or
       any(type(v) is not int or not 0<=v<=2**31-1 for v in dungeon_clear) or dungeon_clear[0]==0 or inventory_response_builder is not None):raise ValueError('Invalid dungeon clear record')
   grant['dungeon_clear']=list(dungeon_clear)
  if attendance_clear is not None:
   from els_server.storage.attendance_2026_commit import AttendanceClearCommit
   if type(attendance_clear) is not AttendanceClearCommit or attendance_clear.character!=self.uid or dungeon_clear is None:raise ValueError('Typed owned attendance clear required')
   grant['attendance518']=attendance_clear.receipt_identity()
  if self.uid!=1001:grant['owner']=self.uid
  if item_plan is not None:
   from els_server.storage.inventory_state import ensure_inventory,grant_items,validate_plan,migrate_potion_bag,migrate_fashion_bag,normalize_legacy_potion_groups
   item_plan=validate_plan(item_plan);grant['items']=item_plan
  digest=hashlib.sha256(proof).hexdigest();plan=json.dumps(grant,sort_keys=True,separators=(',',':'))
  db=transaction if transaction is not None else self._connect()
  if transaction is not None:
   actual=db.execute('PRAGMA database_list').fetchone()[2]
   if not db.in_transaction or Path(actual).resolve()!=self.path.resolve():raise ValueError('Reward transaction database/ownership')
  try:
   if transaction is None:db.execute('BEGIN IMMEDIATE')
   savepoint='attendance_reward_'+uuid.uuid4().hex;db.execute('SAVEPOINT '+savepoint)
   if resonance_source is not None:
    from els_server.storage import resonance_state as er
    er.owner(db,self.uid,self.account_id)
   if item_plan is not None:ensure_inventory(db);migrate_fashion_bag(db);migrate_potion_bag(db)
   existing=db.execute('SELECT proof_sha256,grant_json,response,balance_json FROM reward_receipts WHERE run_id=?',(run_id,)).fetchone()
   if existing:
    saved_grant=json.loads(existing[1])
    if item_plan is not None and 'items' in saved_grant:saved_grant['items']=normalize_legacy_potion_groups(saved_grant['items'])
    # Old committed grants replay their exact original response without a
    # retroactive title bonus, even after enabling this source integration.
    comparable=dict(grant)
    if 'title_economy' not in saved_grant:comparable.pop('title_economy',None)
    if 'title_dungeon' not in saved_grant:comparable.pop('title_dungeon',None)
    if 'attendance518' not in saved_grant:comparable.pop('attendance518',None) # never backfill an old clear
    if 'experience_limit' not in saved_grant:comparable.pop('experience_limit',None)
    if 'resonance_source' not in saved_grant:comparable.pop('resonance_source',None)
    if 'resonance_multiplier' not in saved_grant:comparable.pop('resonance_multiplier',None) # old receipts never receive a top-up
    if existing[0]!=digest or saved_grant!=comparable:raise RewardConflict('Reward retry conflicts with committed evidence or grant')
    reply={'response':bytes(existing[2]),'balances':json.loads(existing[3]),'replayed':True}
    if resonance_source is not None and 'resonance_source' in saved_grant:
     award=er.receipt(db,run_id)
     if award is not None:
      if award['account_id']!=er.owner(db,self.uid,self.account_id) or award['owner']!=self.uid:raise RewardConflict('ERP receipt account changed')
      reply['resonance_award']=award
    if 'title_economy' in saved_grant:
     effect=db.execute('SELECT owner,effect_json FROM reward_title_receipts WHERE run_id=?',(run_id,)).fetchone()
     if effect is None or effect[0]!=self.uid:raise RewardConflict('Missing/mismatched committed title reward')
     reply['title_economy']=json.loads(effect[1])
    if clear_assessment is not None:
     from els_server.storage.local_clear_rules import lookup_db
     reply['local_rules']=lookup_db(db,self.uid,run_id)
    if item_plan is not None:
     saved=db.execute('SELECT items_json FROM reward_inventory_receipts WHERE run_id=?',(run_id,)).fetchone()
     if saved is None:raise RewardConflict('Missing committed inventory receipt')
     reply['items']=normalize_legacy_potion_groups(json.loads(saved[0]))
    db.execute('RELEASE '+savepoint);savepoint=None
    if transaction is None:db.commit()
    return reply
   r=db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(self.uid,)).fetchone()
   validate_balances(r)
   effect=None
   if title_economy is not None:
    from els_server.domain.title_economy import resolve
    effect=resolve(db,self.uid,title_economy,ed,experience,dungeon_clear[0] if title_economy=='clear' else title_dungeon)
    ed,experience=effect['ed'],effect['experience']
   resonance_award=None
   if resonance_source is not None and er.route(db,self.uid,self.account_id)=='resonance':
    resonance_award=er.award(db,self.uid,run_id,proof,resonance_source,experience*grant['resonance_multiplier'],self.account_id)
    experience=0
    if effect is not None:
     # C1 displays this newly committed ERP increment, never the run's K again.
     effect=dict(effect,experience=resonance_award['effective'],resonance_experience=resonance_award['effective'])
     effect['base_experience']=min(effect['base_experience']*grant['resonance_multiplier'],effect['experience']);effect['bonus_experience']=effect['experience']-effect['base_experience']
   if experience_limit is not None and resonance_award is None:
    experience=min(experience,max(0,experience_limit-r[1]))
    if effect is not None:
     effect=dict(effect,experience=experience,base_experience=min(effect['base_experience'],experience))
     effect['bonus_experience']=experience-effect['base_experience']
   updated={'ed':r[0]+ed,'experience':r[1]+experience,'revision':r[2]+1}
   if max(updated.values())>2**63-1:raise ValueError('Reward balance overflow')
   # Level and earned experience commit together, behind the same idempotent
   # receipt. Legacy stores without character identities remain supported.
   if experience and db.execute("SELECT 1 FROM sqlite_master WHERE name='characters' AND type='table'").fetchone():
    from els_server.game_data import client_data
    level=client_data().level_for_experience(updated['experience'])
    db.execute('UPDATE characters SET level=?,revision=revision+1 WHERE uid=? AND level<?',(level,self.uid,level))
   # Ordinary character EXP is never a source of Artifact EXP.
   if clear_assessment is not None:
    from els_server.storage.local_clear_rules import commit as commit_local_rules
    commit_local_rules(db,self.uid,run_id,clear_assessment,artifact_base)
   # Encoding runs inside the transaction. The protocol builder uses
   # per-run grants or verified totals; any failure rolls back everything.
   awarded=grant_items(db,item_plan,self.uid) if item_plan is not None else None
   if challenge_clear is not None:
    from els_server.storage.challenge_state import commit_clear
    commit_clear(db,self.uid,challenge_clear)
   if dungeon_clear is not None:
    map_id,seconds=dungeon_clear
    from els_server.storage.pet_progression import clear as grow_pet
    grow_pet(db,self.uid,seconds)
    previous=db.execute('SELECT seconds FROM dungeon_records WHERE uid=? AND map_id=?',(self.uid,map_id)).fetchone()
    best=min(previous[0],seconds) if previous and seconds else previous[0] if previous else seconds
    if seconds:
     db.execute('INSERT INTO dungeon_records VALUES (?,?,?) ON CONFLICT(uid,map_id) DO UPDATE SET seconds=excluded.seconds',(self.uid,map_id,best))
    from els_server.storage.title_clears import commit as commit_title_clear
    commit_title_clear(db,self.uid,map_id,seconds=seconds)
    response=response_builder(dict(updated),best,dict(effect)) if effect is not None else response_builder(dict(updated),best)
   else:
    response=(inventory_response_builder(dict(updated),[dict(i) for i in awarded]) if inventory_response_builder is not None else response_builder(dict(updated),dict(effect)) if effect is not None else response_builder(dict(updated)))
   if not isinstance(response,bytes) or not 1<=len(response)<=65536:raise ValueError('Invalid reward response')
   db.execute('UPDATE reward_balances SET ed=?,experience=?,revision=? WHERE uid=?',(updated['ed'],updated['experience'],updated['revision'],self.uid))
   db.execute('INSERT INTO reward_receipts VALUES (?,?,?,?,?)',(run_id,digest,plan,response,json.dumps(updated,sort_keys=True)))
   if effect is not None:db.execute('INSERT INTO reward_title_receipts VALUES (?,?,?)',(run_id,self.uid,json.dumps(effect,sort_keys=True,separators=(',',':'))))
   if awarded is not None:db.execute('INSERT INTO reward_inventory_receipts VALUES (?,?)',(run_id,json.dumps(awarded,sort_keys=True)))
   if attendance_clear is not None:attendance_clear.commit(db,self.uid,run_id,dungeon_clear)
   db.execute('RELEASE '+savepoint);savepoint=None
   if transaction is None:db.commit()
   reply={'response':response,'balances':updated,'replayed':False}
   if resonance_award is not None:reply['resonance_award']=resonance_award
   if effect is not None:reply['title_economy']=effect
   if clear_assessment is not None:
    from els_server.storage.local_clear_rules import lookup_db
    reply['local_rules']=lookup_db(db,self.uid,run_id)
   if awarded is not None:reply['items']=awarded
   return reply
  except BaseException:
   if locals().get('savepoint') is not None:
    db.execute('ROLLBACK TO '+savepoint);db.execute('RELEASE '+savepoint)
   if transaction is None:db.rollback()
   raise
  finally:
   if transaction is None:db.close()
