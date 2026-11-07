"""Full bounded queue shutdown, commit failure and redirected private handles."""
import runtime_fixture as h
import asyncio,concurrent.futures,contextlib,json,sqlite3,threading,time,uuid
from unittest.mock import patch
from profile_town import seed
from els_server.storage import coin_writer as m
from els_server.storage.reward_state import RewardState
from els_server.domain.drop_pickup import GROUND_ED
from els_server.domain import dungeon_drops

def until(predicate):
 deadline=time.monotonic()+4
 while not predicate():assert time.monotonic()<deadline;time.sleep(.001)

async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();writers=[];out=dict(passed=False)
 try:
  uid=seed(c,c.alice,'OwnCoinLife',False);path=c.config.state_file;store=RewardState(path,uid,account_id=c.alice['id'])
  def job(index):return dict(operation=str(uuid.uuid5(uuid.NAMESPACE_URL,'own-lifetime-'+str(index))),proof=('own-coin-'+str(index)).encode(),drop_id=100+index,template=min(GROUND_ED),ed=10,dungeon=34710)
  before=store.balances()['ed'];entered=threading.Event();release=threading.Event();encode=dungeon_drops.ground_pickup_notice
  def held(*a,**kw):
   if a[0]==100:entered.set();assert release.wait(5)
   return encode(*a,**kw)
  writer=m.CoinWriter(path);writers.append(writer);closing=None
  with concurrent.futures.ThreadPoolExecutor(17)as pool:
   try:
    with patch.object(dungeon_drops,'ground_pickup_notice',held):
     tasks=[pool.submit(writer.claim,store,**job(0))];assert entered.wait(4)
     for i in range(1,17):tasks.append(pool.submit(writer.claim,store,**job(i)));until(lambda:writer.queue.qsize()==i)
     assert writer.queue.full();closing=threading.Thread(target=writer.close);closing.start();until(lambda:writer.closed)
     assert not any(t.done()for t in tasks);assert store.balances()['ed']==before
     release.set()
     for task in tasks:assert not task.result(4)['replayed']
     closing.join(4);assert not closing.is_alive()
   finally:
    release.set()
    if closing is not None:closing.join(4)
  assert store.balances()['ed']==before+170 and writer.snapshot()['pending']==0
  writer=m.CoinWriter(path);writers.append(writer);transaction=m.write_transaction
  @contextlib.contextmanager
  def failed_commit(db):
   with transaction(db):yield db;raise OSError('Own physical commit failure')
  before=store.balances()['ed']
  with patch.object(m,'write_transaction',failed_commit):
   try:writer.claim(store,**job(50))
   except OSError:pass
   else:raise AssertionError('Failed physical commit reported success')
  assert store.balances()['ed']==before
  writer.claim(store,**job(50));assert store.balances()['ed']==before+10;writer.close()
  # Re-resolve/reopen the private fixed handle when an owned alias redirects.
  target=c.root/'coin-target.sqlite3';alias=c.root/'coin-alias.sqlite3'
  with contextlib.closing(sqlite3.connect(path))as source,contextlib.closing(sqlite3.connect(target))as destination:source.backup(destination)
  alias.symlink_to(path);selected=RewardState(alias,uid,account_id=c.alice['id']);writer=m.CoinWriter(alias);writers.append(writer)
  first=writer.claim(selected,**job(60));alias.unlink();alias.symlink_to(target);second=writer.claim(selected,**job(61))
  assert first['balances']['ed']==before+20 and second['balances']['ed']==before+20
  with contextlib.closing(sqlite3.connect(path))as db:assert db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()==(before+20,)
  # A changed selected store after encoding rolls back its complete receipt.
  previous=selected.uid
  def changed(*a,**kw):
   value=encode(*a,**kw);selected.uid=c.bob['id']+100000;return value
  with patch.object(dungeon_drops,'ground_pickup_notice',changed):
   try:writer.claim(selected,**job(62))
   except ValueError:pass
   else:raise AssertionError('Changed selected store accepted')
   finally:selected.uid=previous
  with contextlib.closing(sqlite3.connect(target))as db:
   assert db.execute('SELECT 1 FROM reward_receipts WHERE run_id=?',(job(62)['operation'],)).fetchone()is None
   assert db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()==(before+20,)
  writer.close()
  out.update(passed=True,full_16_waiting_queue_and_started_claim_drain_before_close=True,no_result_before_actual_commit=True,physical_commit_failure_rolls_back_and_retry_issues_once=True,private_alias_redirection_reopens_correct_file=True,post_encode_store_change_rolls_back_complete_receipt=True,no_queue_debt=True)
 finally:
  for writer in writers:writer.close()
  await c.asyncTearDown();out['owned_runtime_removed']=not c.root.exists()
  (h.H/'coin-writer-lifetime-tests.json').write_text(json.dumps(out,indent=2),'utf8')
 print(json.dumps(out))
asyncio.run(main())
