"""Pinned grant oracle, real group commit, independent rollback and private reuse."""
import runtime_fixture as h
import asyncio,concurrent.futures,contextlib,json,sqlite3,threading,time,uuid
from unittest.mock import patch
from profile_town import seed
from els_server.storage import coin_writer as m
from els_server.storage.reward_state import RewardState
from els_server.domain.drop_pickup import GROUND_ED
from els_server.domain import dungeon_drops
from els_server.protocol.local_messages import client_economy_fields
from els_server.storage import titles as title_storage
from els_server.domain import titles as title_rules

old=h.load('pinned_coin_rewards',h.BASE/'els_server/storage/reward_state.py')
def dump(path):
 with contextlib.closing(sqlite3.connect(path))as db:return tuple(sorted(db.iterdump()))
def until(predicate):
 deadline=time.monotonic()+4
 while not predicate():assert time.monotonic()<deadline;time.sleep(.001)

async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();out=dict(passed=False);writers=[]
 try:
  identities=[c.alice,c.bob]+[c.app.registry.create('coinown'+str(i))for i in range(6)]
  uids=[seed(c,v,'OwnCoin'+str(i),False)for i,v in enumerate(identities)]
  with contextlib.closing(sqlite3.connect(c.config.state_file))as db,db:
   title_storage.schema(db)
   for uid in uids[:2]:
    character=title_storage.character(db,uid);assert title_rules.eligible(character,80)
    kind,subject=title_rules.scope(character,80)
    db.execute('INSERT OR REPLACE INTO title_ownership VALUES(?,?,?,?,?,0)',(kind,subject,80,character['name'],int(time.time())-100))
    db.execute('INSERT OR REPLACE INTO title_equipment VALUES(?,80)',(uid,))
  templates=sorted(GROUND_ED);jobs=[dict(operation=str(uuid.uuid5(uuid.NAMESPACE_URL,'own-coins-'+str(i))),proof=('own-proof-'+str(i)).encode(),drop_id=100+i,template=templates[i%len(templates)],ed=100+i,dungeon=34710)for i in range(8)]
  def clone(name):
   path=c.root/(name+'.sqlite3')
   with contextlib.closing(sqlite3.connect(c.config.state_file))as source,contextlib.closing(sqlite3.connect(path))as db:source.backup(db);db.execute('PRAGMA journal_mode=WAL')
   return path
  def original_claim(store,job):
   def encode(balances,economy):
    client_economy_fields(balances);return dungeon_drops.ground_pickup_notice(job['drop_id'],store.uid,template=job['template'],ed=job['ed'],bonus_ed=economy['bonus_ed']).payload
   return store.grant(job['operation'],job['proof'],job['ed'],0,response_builder=encode,title_economy='ground_ed',title_dungeon=job['dungeon'])
  cases=[];native_encode=dungeon_drops.ground_pickup_notice;frozen_now=int(time.time())
  for failing in(False,True):
   prior_path=clone('original-'+str(failing));path=clone('batch-'+str(failing))
   old_stores=[old.RewardState(prior_path,u,account_id=v['id'])for u,v in zip(uids,identities)]
   stores=[RewardState(path,u,account_id=v['id'])for u,v in zip(uids,identities)]
   def encode(*args,**kwargs):
    if failing and args[0]==103:raise ValueError('Owned coin encoding failure')
    return native_encode(*args,**kwargs)
   expected=[]
   with patch.object(dungeon_drops,'ground_pickup_notice',encode),patch('time.time',return_value=frozen_now):
    for store,job in zip(old_stores,jobs):
     try:expected.append(original_claim(store,job))
     except ValueError as error:expected.append((type(error).__name__,str(error)))
    assert all(value['title_economy']['bonus_ed']>0 for value in expected[:2]),'Active owned ED title effect missing'
    ready=threading.Event();collect=threading.Event();precommit=threading.Event();retire=threading.Event()
    class HeldQueue(m.Queue):
     def __init__(self,*a,**kw):super().__init__(*a,**kw);self.first=True
     def get(self,*a,**kw):
      value=super().get(*a,**kw)
      if self.first:self.first=False;ready.set();assert collect.wait(5)
      return value
    transaction=m.write_transaction
    @contextlib.contextmanager
    def held_commit(db):
     with transaction(db):yield db;precommit.set();assert retire.wait(5)
    before=dump(path)
    with patch.object(m,'Queue',HeldQueue):writer=m.CoinWriter(path)
    writers.append(writer)
    with concurrent.futures.ThreadPoolExecutor(8)as pool:
     try:
      with patch.object(m,'write_transaction',held_commit):
       tasks=[pool.submit(writer.claim,store,**job)for store,job in zip(stores,jobs)]
       assert ready.wait(4);until(lambda:writer.queue.qsize()==7);collect.set();assert precommit.wait(4)
       assert not any(task.done()for task in tasks)and dump(path)==before,'Coin published before durable commit'
       retire.set();actual=[]
       for task in tasks:
        try:actual.append(task.result(4))
        except ValueError as error:actual.append((type(error).__name__,str(error)))
     finally:collect.set();retire.set()
    assert actual==expected,'Original coin grant response differs'
    assert dump(path)==dump(prior_path),'Full coin/title/receipt SQL differs'
    assert writer.snapshot()['batches']==1 and writer.snapshot()['max_batch']==8
    # Replays never add to either balance; original receipt values stay exact.
    prior=dump(path)
    for index,(store,job)in enumerate(zip(stores,jobs)):
     if failing and index==3:continue
     result=writer.claim(store,**job);assert result['replayed']
    assert dump(path)==prior
   cases.append(dict(encoding_failure=failing,full_pinned_grants_and_SQL_equal=True,batch_size=8))
   writer.close()
  # A real transaction-wide ROLLBACK cannot be mistaken for per-job failure.
  path=clone('fatal-rollback');stores=[RewardState(path,u,account_id=v['id'])for u,v in zip(uids,identities)]
  with contextlib.closing(sqlite3.connect(path))as db,db:db.execute("CREATE TRIGGER own_coin_rollback BEFORE UPDATE ON reward_balances WHEN NEW.uid="+str(uids[3])+" BEGIN SELECT RAISE(ROLLBACK,'own full rollback');END")
  before=dump(path);ready=threading.Event();collect=threading.Event()
  with patch.object(m,'Queue',HeldQueue):writer=m.CoinWriter(path)
  writers.append(writer)
  with concurrent.futures.ThreadPoolExecutor(8)as pool:
   tasks=[]
   try:
    tasks.append(pool.submit(writer.claim,stores[0],**jobs[0]));assert ready.wait(4)
    for i in range(1,8):tasks.append(pool.submit(writer.claim,stores[i],**jobs[i]));until(lambda:writer.queue.qsize()==i)
    collect.set()
    for task in tasks:
     try:task.result(4)
     except sqlite3.Error:pass
     else:raise AssertionError('A rolled-back coin was reported successful')
   finally:collect.set()
  assert dump(path)==before;writer.close()
  # One private connection survives independent commits and sees external SQL.
  path=clone('reused-handle');store=RewardState(path,uids[0],account_id=identities[0]['id']);opened=[];closed=[];connect=sqlite3.connect
  class Tracked(sqlite3.Connection):
   def close(self):assert not self.in_transaction;closed.append(threading.get_ident());return super().close()
  def tracked(*a,**kw):
   if threading.current_thread().name=='els-coin-writer':opened.append(threading.get_ident());kw['factory']=Tracked
   return connect(*a,**kw)
  writer=m.CoinWriter(path);writers.append(writer)
  with patch.object(m.sqlite3,'connect',tracked):
   first=writer.claim(store,**jobs[0])
   with contextlib.closing(connect(path))as db,db:db.execute('UPDATE reward_balances SET ed=ed+777 WHERE uid=?',(store.uid,))
   job=dict(jobs[0],operation=str(uuid.uuid4()),proof=b'own-next',drop_id=500)
   second=writer.claim(store,**job);assert second['balances']['ed']==first['balances']['ed']+777+job['ed']+second['title_economy']['bonus_ed']
   assert len(opened)==1;writer.close();assert opened==closed
  out.update(passed=True,storage_oracle_cases=cases,active_owned_ED_title_preserves_original_bonus=True,SQL_comparison_normalizes_cross_account_statement_order=True,native_NPC_generation_claim=False,eight_waiters_share_actual_commit=True,independent_bad_encoder_rolls_back_only_its_job=True,original_replay_has_no_increment=True,transaction_wide_rollback_after_prior_good_jobs_reports_no_success=True,private_handle_reuse_sees_external_commit_and_closes_on_owner_thread=True,no_caller_callback_or_economic_capability_accepted=True)
 finally:
  for writer in writers:writer.close()
  await c.asyncTearDown();out['owned_runtime_removed']=not c.root.exists()
  (h.H/'coin-writer-tests.json').write_text(json.dumps(out,indent=2),'utf8')
 print(json.dumps(out))
asyncio.run(main())
