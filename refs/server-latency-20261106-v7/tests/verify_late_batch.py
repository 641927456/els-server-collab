"""Jobs arriving after preparation began share one actual durable commit."""
import runtime_fixture as h
import asyncio,concurrent.futures,contextlib,json,sqlite3,threading,time,uuid
from unittest.mock import patch
from profile_town import seed
from els_server.storage import coin_writer as coins,death_writer as deaths
from els_server.storage.reward_state import RewardState
from els_server.storage.read_scope import ReadConnections
from els_server.domain.drop_pickup import GROUND_ED

def until(predicate):
 deadline=time.monotonic()+5
 while not predicate():
  if time.monotonic()>deadline:raise AssertionError('Owned synchronization deadline')
  time.sleep(.001)

async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();reports=[];candidate='--candidate'in __import__('sys').argv
 try:
  uid=seed(c,c.alice,'OwnLate7',False)
  for lane in ['death','coin']:
   module=deaths if lane=='death'else coins
   entered=threading.Event();continue_first=threading.Event();at_commit=threading.Event();allow_commit=threading.Event();second_prepared=threading.Event();commits=[]
   transaction=module.write_transaction
   @contextlib.contextmanager
   def held_commit(db):
    with transaction(db):
     yield db
     commits.append(1);at_commit.set();assert allow_commit.wait(5)
   readers=ReadConnections();writer=deaths.DeathWriter(c.config.state_file,readers)if lane=='death'else coins.CoinWriter(c.config.state_file)
   if lane=='death':
    with contextlib.closing(sqlite3.connect(c.config.state_file))as db,db:db.execute('CREATE TABLE own_late_deaths(value INTEGER)')
    def prepare(index):
     def call(db):
      db.execute('INSERT INTO own_late_deaths VALUES(?)',(index,))
      if index==1:entered.set();assert continue_first.wait(5)
      else:second_prepared.set()
      return index
     return writer.submit(c.config.state_file,call)
    def value():
     with contextlib.closing(sqlite3.connect(c.config.state_file))as db:return db.execute('SELECT COUNT(*) FROM own_late_deaths').fetchone()[0]
    extra=contextlib.nullcontext()
   else:
    store=RewardState(c.config.state_file,uid,account_id=c.alice['id']);grant=coins.CoinWriter._grant
    def delayed(db,job):
     result=grant(db,job)
     if job[4]==1:entered.set();assert continue_first.wait(5)
     else:second_prepared.set()
     return result
    extra=patch.object(coins.CoinWriter,'_grant',staticmethod(delayed))
    def prepare(index):return writer.claim(store,str(uuid.uuid4()),b'owned-late-batch-'+str(index).encode(),drop_id=index,template=min(GROUND_ED),ed=10,dungeon=34710)
    def value():return store.balances()['ed']
   before=value()
   try:
    with extra,patch.object(module,'write_transaction',held_commit),concurrent.futures.ThreadPoolExecutor(2)as pool:
     try:
      first=pool.submit(prepare,1);assert entered.wait(5)
      second=pool.submit(prepare,2);until(lambda:writer.queue.qsize()==1)
      continue_first.set();assert at_commit.wait(5)
      assert second_prepared.is_set()==candidate
      assert not first.done()and not second.done()and value()==before
      allow_commit.set();first.result(5);second.result(5)
     finally:continue_first.set();allow_commit.set()
    assert len(commits)==(1 if candidate else 2)
    assert value()==before+(2 if lane=='death'else 20)
    report=dict(lane=lane,late_arrival_actual_commits=len(commits),no_reply_before_commit=True,cold_SQL_exact=True,maximum_batch=writer.snapshot().get('maximum_batch',writer.snapshot().get('max_batch')))
    reports.append(report)
   finally:writer.close();readers.close()
 finally:await c.asyncTearDown()
 out=dict(passed=True,candidate=candidate,cases=reports,owned_runtime_removed=not c.root.exists())
 (h.H/('late-batch-'+('candidate'if candidate else'baseline')+'.json')).write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
asyncio.run(main())
