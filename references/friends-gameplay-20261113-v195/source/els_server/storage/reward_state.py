"""Atomic local ED/experience receipts. Protocol integration needs verified fields."""
import hashlib,json,sqlite3,uuid
from contextlib import closing
from pathlib import Path
from els_server.storage.read_scope import canonical_path
from els_server.storage.character_schema import character_uid,migrate_character_schema

class RewardConflict(ValueError):pass
def validate_balances(row):
 if row is None or len(row)!=3 or any(type(v) is not int or not 0<=v<=2**63-1 for v in row):raise ValueError('Invalid persisted reward balances')
 return dict(zip(('ed','experience','revision'),row))
def ensure_reward_tables(db):
 migrate_character_schema(db)
 db.execute('CREATE TABLE IF NOT EXISTS reward_balances (uid INTEGER PRIMARY KEY CHECK(uid>=1001), ed INTEGER NOT NULL CHECK(ed>=0), experience INTEGER NOT NULL CHECK(experience>=0), revision INTEGER NOT NULL CHECK(revision>=0))')
 db.execute('CREATE TABLE IF NOT EXISTS reward_receipts (run_id TEXT PRIMARY KEY, proof_sha256 TEXT NOT NULL, grant_json TEXT NOT NULL, response BLOB NOT NULL, balance_json TEXT NOT NULL)')
 db.execute('CREATE TABLE IF NOT EXISTS reward_title_receipts (run_id TEXT PRIMARY KEY REFERENCES reward_receipts(run_id), owner INTEGER NOT NULL, effect_json TEXT NOT NULL)')
 db.execute('CREATE TABLE IF NOT EXISTS dungeon_records (uid INTEGER NOT NULL, map_id INTEGER NOT NULL, seconds INTEGER NOT NULL CHECK(seconds>0 AND seconds<=2147483647), PRIMARY KEY(uid,map_id))')

class RewardState:
 def __init__(self,path,uid=1001,*,account_id=None):
  self.uid=character_uid(uid)
  self.account_id=account_id
  self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
  from els_server.storage.initialization_checks import read_ready,reward_ready
  with closing(self._connect()) as db:
   if not read_ready(db,reward_ready,self.uid):
    with write_transaction(db):
     if not reward_ready(db,self.uid):
       ensure_reward_tables(db)
       db.execute('INSERT OR IGNORE INTO reward_balances VALUES (?,0,0,0)',(self.uid,))
 def _connect(self):return sqlite3.connect(self.path,timeout=10)
 def balances(self):
  db=self._connect()
  try:r=db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(self.uid,)).fetchone()
  finally:db.close()
  return validate_balances(r)
 def grant(self,run_id,proof,ed,experience,response_builder=None,item_plan=None,inventory_response_builder=None,*,dungeon_clear=None,challenge_clear=None,transaction=None,clear_assessment=None,artifact_base=None,title_economy=None,title_dungeon=None,attendance_clear=None,experience_limit=None,resonance_source=None,raid_reward_source=None,silver_source=None,daily_special=None,random_mission=None,dungeon_result=None,giant_task=None,dungeon_drop=False):
  # A run UUID is allocated by the authenticated server, never by a client.
  if not isinstance(run_id,str) or str(uuid.UUID(run_id))!=run_id:raise ValueError('Noncanonical reward run UUID')
  if not isinstance(proof,bytes) or not proof or len(proof)>8192:raise ValueError('Reward evidence bound')
  if any(type(n) is not int or not 0<=n<=2**63-1 for n in (ed,experience)):raise ValueError('Reward amount bound')
  if inventory_response_builder is not None:
   if response_builder is not None or item_plan is None or not callable(inventory_response_builder):raise ValueError('Inventory response requires one builder and an item plan')
  elif not callable(response_builder):raise ValueError('Reward response builder required')
  grant={'ed':ed,'experience':experience}
  if giant_task is not None:
   from els_server.domain.giant_daily_tasks import Task
   if type(giant_task)is not Task or dungeon_clear is None or giant_task.owner!=self.uid or giant_task.operation!=run_id or giant_task.path!=self.path.resolve()or dungeon_clear[0]!=giant_task.dungeon or challenge_clear is not None:raise ValueError('Giant task reward source identity')
   grant['giant_daily_task']=giant_task.identity()
  if random_mission is not None:
   from els_server.domain.random_mission_flow import require_permit
   require_permit(random_mission,self.uid,run_id,experience)
   if dungeon_clear is None or transaction is None or random_mission.session.account.reward_store is not self or random_mission.path.resolve()!=self.path.resolve()or dungeon_clear[0]!=json.loads(random_mission.row['context_json'])['dungeon']:raise ValueError('Mission original clear writer required')
   grant['random_mission']=random_mission.identity()
  if silver_source is not None:
   from els_server.domain.silver_mirror_rewards import validate_source as _mirror_source
   source=_mirror_source(silver_source)
   if daily_special is not None or raid_reward_source is not None or transaction is not source.db or source.owner!=self.uid or source.run_id!=run_id or source.proof_sha256!=hashlib.sha256(proof).hexdigest():raise ValueError('Mirror reward source operation/owner/writer/proof')
   grant['silver_mirror_source']={'run_id':run_id,'proof_sha256':source.proof_sha256}
  if daily_special is not None and raid_reward_source is not None:
   # The ordinary finite clear uses an independent sealed inventory plan.
   # Daily items still pass their own factory; Raid phase/box/pity cannot mix.
   from els_server.domain.raid_reward_items import validate_source as _ordinary_source
   if _ordinary_source(raid_reward_source).kind!='ordinary':raise ValueError('Daily-special and Raid typed sources are mutually exclusive')
  if raid_reward_source is not None:
   from els_server.domain.raid_reward_items import validate_source as _raid_source
   source=_raid_source(raid_reward_source)
   if transaction is None or source.owner!=self.uid or source.operation!=run_id:raise ValueError('Raid reward source operation/owner/writer')
   grant['raid_reward_source']=source.receipt_identity()
  if resonance_source is not None:
   if resonance_source not in ('kill','clear') or (resonance_source=='clear')!=(dungeon_clear is not None):raise ValueError('ERP source boundary')
   grant['resonance_source']=resonance_source
   from els_server.domain.resonance import experience_multiplier
   grant['resonance_multiplier']=experience_multiplier()
   from els_server.domain.hot_time import ordinary_multiplier
   grant['hot_time_ordinary_multiplier']=ordinary_multiplier()
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
  if daily_special is not None:
   from els_server.domain.ariel_daily_special import DailySpecialClear
   if type(daily_special)is not DailySpecialClear or daily_special.character!=self.uid or daily_special.reward_run_id!=run_id or dungeon_clear is None or daily_special.dungeon!=dungeon_clear[0]:raise ValueError('Typed owned daily-special clear required')
   grant['ariel_daily_special']=daily_special.receipt_identity()
  if dungeon_result is not None:
   from els_server.domain.dungeon_result_rules import Assessment
   if(type(dungeon_result)is not Assessment or dungeon_result.uid!=self.uid or dungeon_result.run_id!=run_id
      or dungeon_clear is None or dungeon_result.dungeon!=dungeon_clear[0] or title_economy!='clear'):
    raise ValueError('Owned authoritative dungeon result clear required')
  if self.uid!=1001:grant['owner']=self.uid
  if item_plan is not None:
   from els_server.storage.inventory_state import ensure_inventory,grant_items,validate_plan,migrate_potion_bag,migrate_fashion_bag,normalize_legacy_potion_groups
   item_plan=validate_plan(item_plan,raid_reward_source=raid_reward_source,silver_source=silver_source);grant['items']=item_plan
  digest=hashlib.sha256(proof).hexdigest();plan=json.dumps(grant,sort_keys=True,separators=(',',':'))
  db=transaction if transaction is not None else self._connect()
  if transaction is not None:
   actual=db.execute('PRAGMA database_list').fetchone()[2]
   if not db.in_transaction or canonical_path(actual)!=canonical_path(self.path):raise ValueError('Reward transaction database/ownership')
  acquired=None
  try:
   if transaction is None:acquired=begin_write(db)
   savepoint='attendance_reward_'+uuid.uuid4().hex;db.execute('SAVEPOINT '+savepoint)
   if resonance_source is not None:
    from els_server.storage import resonance_state as er
    er.owner(db,self.uid,self.account_id)
   if item_plan is not None:ensure_inventory(db);migrate_fashion_bag(db);migrate_potion_bag(db)
   if random_mission is not None:require_permit(random_mission,self.uid,run_id,grant['experience'],db)
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
    if 'giant_daily_task' not in saved_grant:comparable.pop('giant_daily_task',None) # never backfill old clears
    if 'ariel_daily_special' not in saved_grant:comparable.pop('ariel_daily_special',None) # never top up an old clear
    if 'experience_limit' not in saved_grant:comparable.pop('experience_limit',None)
    if 'resonance_source' not in saved_grant:comparable.pop('resonance_source',None)
    if 'resonance_multiplier' not in saved_grant:comparable.pop('resonance_multiplier',None) # old receipts never receive a top-up
    if 'hot_time_ordinary_multiplier' in saved_grant:comparable['hot_time_ordinary_multiplier']=saved_grant['hot_time_ordinary_multiplier']
    else:comparable.pop('hot_time_ordinary_multiplier',None) # exact historical grant, no top-up
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
    if 'ariel_daily_special' in saved_grant:
     from els_server.storage.ariel_daily_special import lookup
     reply['ariel_daily_special']=lookup(db,run_id,self.uid)
     from els_server.storage.ariel_daily_special import notification
     from els_server.storage.ariel_attendance import clock
     import time
     reply['ariel_daily_status']=notification(db,daily_special.account,self.uid,clock(time.time))
     daily_special.validate()
    if item_plan is not None or 'ariel_daily_special' in saved_grant or 'giant_daily_task'in saved_grant:
     from els_server.storage.inventory_state import normalize_legacy_potion_groups
     saved=db.execute('SELECT items_json FROM reward_inventory_receipts WHERE run_id=?',(run_id,)).fetchone()
     if saved is None:raise RewardConflict('Missing committed inventory receipt')
     reply['items']=normalize_legacy_potion_groups(json.loads(saved[0]))
    db.execute('RELEASE '+savepoint);savepoint=None
    if transaction is None:commit_write(db)
    return reply
   r=db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(self.uid,)).fetchone()
   validate_balances(r)
   # Resolve ordinary/ERP once, after immutable receipt replay. Leveling
   # assistance is paid only on an ordinary full clear, never into ERP.
   experience_route=er.route(db,self.uid,self.account_id) if resonance_source is not None else None
   leveling=None
   if resonance_source=='clear' and experience_route=='ordinary':
    from els_server.domain.formal_pve_economy import leveling_multiplier
    multiplier=leveling_multiplier(dungeon_clear[0])
    if multiplier!=1:
     from els_server.storage.legacy_pve_exp import run_total
     kill_base=run_total(db,self.uid,run_id,clear_basis=True)
     leveling=dict(multiplier=multiplier,kill_experience=kill_base,clear_experience=experience)
     experience+=(kill_base+experience)*(multiplier-1)
   if experience_route=='ordinary':
    experience*=grant['hot_time_ordinary_multiplier']
   effect=None
   if title_economy is not None:
    from els_server.domain.title_economy import resolve
    effect=resolve(db,self.uid,title_economy,ed,experience,dungeon_clear[0] if title_economy=='clear' else title_dungeon)
    ed,experience=effect['ed'],effect['experience']
    if leveling is not None:effect['leveling_experience']=leveling
   if dungeon_result is not None:
    # The award is a fixed share of this authoritative clear only. Neither
    # score magnitude nor the number of awards can enlarge the bonus rate.
    result_effect=dungeon_result.identity()
    bonus_ed=ed*dungeon_result.bonus_bp//10000
    bonus_experience=experience*dungeon_result.bonus_bp//10000
    result_effect.update(base_ed=ed,base_experience=experience,offered_ed=bonus_ed,offered_experience=bonus_experience)
    ed+=bonus_ed;experience+=bonus_experience
    effect=dict(effect,ed=ed,experience=experience,bonus_ed=effect['bonus_ed']+bonus_ed,
        bonus_experience=effect['bonus_experience']+bonus_experience,dungeon_result=result_effect)
   if random_mission is not None:
    require_permit(random_mission,self.uid,run_id,grant['experience'],db)
    experience_before_mission=experience
    experience+=random_mission.bonus
    if effect is not None:effect=dict(effect,experience=experience,bonus_experience=effect['bonus_experience']+random_mission.bonus)
   resonance_award=None
   if experience_route=='resonance':
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
   if random_mission is not None and effect is not None:
    if resonance_award is not None:
     mission_paid=resonance_award['effective']>experience_before_mission*grant['resonance_multiplier']
    else:
     mission_paid=experience>experience_before_mission
    if mission_paid:effect['random_mission_percent']=grant['random_mission']['percent']
   if dungeon_result is not None:
    result_effect['applied_ed']=bonus_ed
    result_effect['ordinary_experience']=max(0,min(bonus_experience,experience-result_effect['base_experience']))if resonance_award is None else 0
    result_effect['resonance_experience']=(max(0,min(bonus_experience*grant['resonance_multiplier'],
        resonance_award['effective']-result_effect['base_experience']*grant['resonance_multiplier']))if resonance_award is not None else 0)
   updated={'ed':r[0]+ed,'experience':r[1]+experience,'revision':r[2]+1}
   if max(updated.values())>2**63-1:raise ValueError('Reward balance overflow')
   # Level and earned experience commit together, behind the same idempotent
   # receipt. Legacy stores without character identities remain supported.
   level_change=None
   if experience and db.execute("SELECT 1 FROM sqlite_master WHERE name='characters' AND type='table'").fetchone():
    from els_server.game_data import client_data
    level=client_data().level_for_experience(updated['experience'])
    old_level=db.execute('SELECT level FROM characters WHERE uid=?',(self.uid,)).fetchone()
    changed=db.execute('UPDATE characters SET level=?,revision=revision+1 WHERE uid=? AND level<?',(level,self.uid,level)).rowcount
    if changed:
     level_change=(old_level[0],level)
     from els_server.storage.normal_fatigue import level_up as normal_fatigue_level_up
     normal_fatigue_level_up(db,self.path,self.uid,self.account_id,run_id,digest,old_level[0],level)
   # Ordinary character EXP is never a source of Artifact EXP.
   if clear_assessment is not None:
    from els_server.storage.local_clear_rules import commit as commit_local_rules
    commit_local_rules(db,self.uid,run_id,clear_assessment,artifact_base)
   # Encoding runs inside the transaction. The protocol builder uses
   # per-run grants or verified totals; any failure rolls back everything.
   from els_server.storage.force_reward_mail import is_clear_source
   from els_server.domain.force_drop_balance import managed as force_reward
   ordinary_last=(item_plan is not None and dungeon_clear is not None and
       raid_reward_source is not None and is_clear_source(raid_reward_source) and
       any(force_reward(p['template']) for p in item_plan))
   awarded=None
   if item_plan is not None:
    awarded=[] if ordinary_last else grant_items(db,item_plan,self.uid,raid_reward_source=raid_reward_source,silver_source=silver_source,
        dungeon_drop=dungeon_drop or dungeon_clear is not None or inventory_response_builder is not None)
   giant_task_notice=None
   if giant_task is not None:
    from els_server.domain.giant_daily_tasks import grant as grant_giant_task,notice as giant_notice,REWARDS as giant_rewards
    task_items=grant_giant_task(db,giant_task,self.uid,run_id,dungeon_clear)
    awarded=list({i['uid']:i for i in [*(awarded or []),*task_items]}.values())
    from els_server.domain.dungeon_drops import pickup_inventory_notice
    from els_server.protocol.protocol_codec import encode_event
    if awarded:encode_event(pickup_inventory_notice(awarded))
    if task_items:
     giant_task_notice=giant_notice(giant_rewards[giant_task.dungeon]);encode_event(giant_task_notice)
   daily_detail=None;daily_status=None
   if daily_special is not None:
    from els_server.storage import ariel_daily_special as daily_store
    daily_detail,daily_items,daily_status=daily_store.grant(db,daily_special,self.uid,run_id,dungeon_clear)
    awarded=list({i['uid']:i for i in [*(awarded or []),*daily_items]}.values())
    from els_server.domain.dungeon_drops import pickup_inventory_notice
    from els_server.protocol.protocol_codec import encode_event
    if awarded:encode_event(pickup_inventory_notice(awarded))
   if ordinary_last:
    ordinary_items=grant_items(db,item_plan,self.uid,raid_reward_source=raid_reward_source,dungeon_drop=True)
    awarded=list({i['uid']:i for i in [*(awarded or []),*ordinary_items]}.values())
   if challenge_clear is not None:
    from els_server.storage.challenge_state import commit_clear
    commit_clear(db,self.uid,challenge_clear)
   pet_notices=[]
   if dungeon_clear is not None:
    map_id,seconds=dungeon_clear
    from els_server.storage.pet_progression import clear as grow_pet
    grow_pet(db,self.uid,seconds,notices=pet_notices)
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
   if dungeon_result is not None:
    from els_server.domain.dungeon_result_rules import result_payload
    response=result_payload(response,dungeon_result)
   if random_mission is not None:random_mission.validate(db)
   if daily_special is not None:daily_special.validate()
   db.execute('UPDATE reward_balances SET ed=?,experience=?,revision=? WHERE uid=?',(updated['ed'],updated['experience'],updated['revision'],self.uid))
   db.execute('INSERT INTO reward_receipts VALUES (?,?,?,?,?)',(run_id,digest,plan,response,json.dumps(updated,sort_keys=True)))
   if dungeon_clear is not None and dungeon_clear[0]==38300:
    from els_server.storage.environment_buffs import gate_clear
    gate_clear(db,self.uid,run_id)
   if effect is not None:db.execute('INSERT INTO reward_title_receipts VALUES (?,?,?)',(run_id,self.uid,json.dumps(effect,sort_keys=True,separators=(',',':'))))
   if awarded is not None:db.execute('INSERT INTO reward_inventory_receipts VALUES (?,?)',(run_id,json.dumps(awarded,sort_keys=True)))
   if attendance_clear is not None:attendance_clear.commit(db,self.uid,run_id,dungeon_clear)
   if daily_special is not None:daily_store.save(db,run_id,self.uid,daily_detail)
   from els_server.domain.gameplay_announcements import progression
   announcements=progression(db,self.uid,ordinary=level_change,resonance=resonance_award)
   db.execute('RELEASE '+savepoint);savepoint=None
   if transaction is None:commit_write(db)
   reply={'response':response,'balances':updated,'replayed':False}
   if announcements:reply['announcements']=announcements
   if pet_notices:reply['pet_notices']=pet_notices
   if resonance_award is not None:reply['resonance_award']=resonance_award
   if effect is not None:reply['title_economy']=effect
   if clear_assessment is not None:
    from els_server.storage.local_clear_rules import lookup_db
    reply['local_rules']=lookup_db(db,self.uid,run_id)
   if daily_special is not None:reply.update(ariel_daily_special=daily_detail,ariel_daily_status=daily_status)
   if awarded is not None:reply['items']=awarded
   if giant_task_notice is not None:reply['giant_task_notice']=giant_task_notice
   return reply
  except BaseException:
   # FULL/IO failures can roll back the outer transaction and its savepoints.
   if locals().get('savepoint') is not None and db.in_transaction:
    db.execute('ROLLBACK TO '+savepoint);db.execute('RELEASE '+savepoint)
   if transaction is None:db.rollback()
   raise
  finally:
   if transaction is None:
    try:db.close()
    finally:
     if acquired is not None:end_write(acquired,failed=__import__('sys').exc_info()[0] is not None)

from els_server.storage.sqlite_timing import write_transaction

from els_server.storage.sqlite_timing import begin_write,end_write,commit_write
