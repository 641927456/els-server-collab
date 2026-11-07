"""Pinned native notice/escrow oracle; negative reads and writer rechecks."""
import runtime_fixture as h
import ast,asyncio,json,sqlite3,time
from contextlib import closing
from unittest.mock import patch
from els_server.domain import online_2026_campaign as campaign
from els_server.domain.online_2026_clock import OnlineTitleClock
from els_server.storage.online_2026_progress import OnlineTitleProgress
from els_server.storage import online_2026_delivery as delivery
from els_server.storage.sqlite_timing import write_transaction
from profile_town import seed

old_delivery=h.load('pinned_title_delivery',h.BASE/'els_server/storage/online_2026_delivery.py')
namespace=dict(vars(campaign));namespace['OnlineTitleDelivery']=old_delivery.OnlineTitleDelivery
old_mail=h.load('pinned_title_mail_notice',h.BASE/'els_server/domain/online_2026_mail_notice.py')
namespace['OnlineMailNotice']=old_mail.OnlineMailNotice
namespace['MailNoticePolicy']=old_mail.MailNoticePolicy
tree=ast.parse((h.BASE/'els_server/domain/online_2026_campaign.py').read_bytes())
node=next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name=='OnlineTitleCampaign')
exec(compile(ast.Module(body=[node],type_ignores=[]),'pinned-v5-title-notices','exec'),namespace)

def dump(path):
 with closing(sqlite3.connect(path))as db:return tuple(db.iterdump())

async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();out=dict(passed=False);cases=0
 try:
  uid=seed(c,c.alice,'OwnTitleRead');peer=await c.peer(c.alice);await peer.roster();await peer.enter_town(uid);await c.server.periodics.close()
  s=c.app.playing[c.alice['id']];source=s.activity2026_awards.online.title
  now=int(time.time());mono=[10.]
  with closing(sqlite3.connect(c.config.state_file))as db,db:
   db.execute('DELETE FROM online2026_spans WHERE campaign=?AND character=?',(source.clock.campaign,uid))
   week,lo,hi=db.execute('SELECT week,starts,ends FROM online2026_periods WHERE campaign=?AND starts<=?AND ends>?',(source.clock.campaign,now,now)).fetchone()
  assert lo<=now-1801 and now+1<hi
  def clone(label,seconds,*,old=False):
   path=c.root/(label+'.sqlite3')
   with closing(sqlite3.connect(c.config.state_file))as original,closing(sqlite3.connect(path))as db:
    original.backup(db)
    db.execute('PRAGMA journal_mode=WAL')
    with write_transaction(db):
     repo=OnlineTitleProgress(db,source.clock.selection_bytes,campaign=source.clock.campaign)
     if seconds:repo.record_span(account=c.alice['id'],character=uid,week=week,operation='owned-'+str(seconds),starts=now-seconds,ends=now)
   identity=(str(path),c.alice['id'],uid,99)
   clock=OnlineTitleClock(source.clock.selection_bytes,campaign=source.clock.campaign,eligibility=lambda _:identity,monotonic=lambda:mono[0],epoch=lambda:float(now));clock.identity=identity
   cls=namespace['OnlineTitleCampaign']if old else campaign.OnlineTitleCampaign
   policy=old_mail.MailNoticePolicy(source.mail_policy.flag,source.mail_policy.preview_limit)if old else source.mail_policy
   flow=cls(clock,title_link=source.link,record=source.record,enabled=lambda _:True,mail_identity=lambda _:identity,mail_policy=policy,local_policy=campaign.LOCAL_POLICY)
   return path,flow
  counts={};negative=None
  for seconds in(0,1799,1800,1801):
   results=[];states=[]
   for old in(True,False):
    label=('original-'if old else'candidate-')+str(seconds);path,flow=clone(label,seconds,old=old);queries=[];connect=sqlite3.connect
    def traced(*args,**kwargs):
     db=connect(*args,**kwargs);db.set_trace_callback(queries.append);return db
    with patch.object(sqlite3,'connect',traced):events=flow.notifications(s)
    first=list(events);mono[0]+=2
    with patch.object(sqlite3,'connect',traced):events2=flow.notifications(s)
    results.append((first,events2));states.append(dump(path))
    counts[label]=sum(q=='BEGIN IMMEDIATE'for q in queries)
    if seconds<1800 and not old:assert counts[label]==0,queries
    if seconds>=1800 and not old:
     assert counts[label]==1,queries
     with closing(sqlite3.connect(path))as db:
      assert db.execute('SELECT COUNT(*)FROM online2026_delivery WHERE character=?',(uid,)).fetchone()==(1,)
    if seconds==0 and not old:negative=(path,flow)
   assert results[0]==results[1],(seconds,'Native messages differ')
   assert states[0]==states[1],(seconds,'Escrow/receipt/player SQL differs')
   cases+=1
  no_period=[];no_period_states=[]
  for old in(True,False):
   path,flow=clone('no-period-'+str(old),0,old=old)
   with closing(sqlite3.connect(path))as db,db:db.execute('DELETE FROM online2026_periods WHERE campaign=?',(source.clock.campaign,))
   no_period.append(flow.notifications(s));no_period_states.append(dump(path))
  assert no_period[0]==no_period[1]and no_period_states[0]==no_period_states[1]
  cases+=1
  # A real WAL writer cannot block a negative notification's RO projection.
  path,flow=negative;flow._force=True;mono[0]+=2
  with closing(sqlite3.connect(path))as blocker:
   blocker.execute('BEGIN IMMEDIATE');assert flow.notifications(s)is not None
   assert not flow._force,'A busy error was swallowed instead of completing the readonly scan'
   blocker.rollback()
  from els_server.storage.read_scope import committed_reads,snapshot_connection
  from els_server.domain import online_2026_mail_notice
  with committed_reads(connections=c.app.read_connections):
   flow._force=True;mono[0]+=2;flow.notifications(s)
   with snapshot_connection(path)as db:assert db.row_factory is None and not db.in_transaction
   flow._force=True;mono[0]+=2
   with patch.object(online_2026_mail_notice,'snapshot',side_effect=ValueError('Owned mail read failure')):
    try:flow.notifications(s)
    except ValueError as error:assert str(error)=='Owned mail read failure'
    else:raise AssertionError('Mail read error hidden')
   with snapshot_connection(path)as db:
    assert db.row_factory is None and not db.in_transaction
    assert db.execute('SELECT 1').fetchone()==(1,),'Mail row factory leaked to another reader'
  # Preview is not a permit: changing the owner before the writer must fail.
  path,flow=clone('changed-owner',1800)
  with closing(sqlite3.connect(path))as db:
   db.execute('BEGIN');repo=OnlineTitleProgress(db,source.clock.selection_bytes,campaign=source.clock.campaign)
   assert delivery.OnlineTitleDelivery(repo,source.link).preview(account=c.alice['id'],character=uid,week=week,now=now)[0]is None;db.rollback()
   with write_transaction(db):db.execute('UPDATE character_owners SET account_id=?WHERE uid=?',(c.bob['id'],uid))
   before=dump(path)
   try:
    with write_transaction(db):delivery.OnlineTitleDelivery(repo,source.link).issue(account=c.alice['id'],character=uid,week=week,now=now)
   except ValueError:pass
   else:raise AssertionError('Stale positive preview authorized changed owner')
   assert dump(path)==before
  # Partial escrow writes before an encoder/storage error remain atomic.
  path,flow=clone('issue-rollback',1800);before=dump(path)
  from els_server.storage import mail_attachments
  put=mail_attachments.put
  def rejected(*args,**kwargs):put(*args,**kwargs);raise ValueError('Owned attachment failure')
  with patch.object(mail_attachments,'put',rejected):
   try:flow.notifications(s)
   except ValueError:pass
   else:raise AssertionError('Partial issuance failure hidden')
  assert dump(path)==before
  assert flow._force,'Failed issuance consumed notification scan'
  mono[0]+=2;flow.notifications(s)
  with closing(sqlite3.connect(path))as db:assert db.execute('SELECT COUNT(*)FROM online2026_delivery WHERE character=?',(uid,)).fetchone()==(1,)
  path,flow=clone('concurrent-issuers',1800)
  import threading,concurrent.futures
  barrier=threading.Barrier(2)
  def issue_once():
   with closing(sqlite3.connect(path))as db:
    barrier.wait()
    with write_transaction(db):
     repo=OnlineTitleProgress(db,source.clock.selection_bytes,campaign=source.clock.campaign)
     return delivery.OnlineTitleDelivery(repo,source.link).issue(account=c.alice['id'],character=uid,week=week,now=now)['status']
  with concurrent.futures.ThreadPoolExecutor(2)as executor:statuses=sorted(executor.map(lambda _:issue_once(),range(2)))
  assert statuses==['already_issued','issued'],statuses
  with closing(sqlite3.connect(path))as db:assert db.execute('SELECT COUNT(*)FROM online2026_delivery WHERE character=?',(uid,)).fetchone()==(1,)
  out.update(passed=True,pinned_v5_native_messages_and_entire_SQL_equal_cases=cases,writer_begins=counts,negative_notice_works_while_WAL_writer_active=True,positive_preview_cannot_authorize_changed_owner=True,partial_escrow_failure_rolls_back_and_retry_issues_once=True,two_concurrent_issuers_mint_once=True,pooled_mail_reader_factory_and_transaction_restored_on_success_and_failure=True,controlled_server_time_fixture=True,native_elapsed_30_minutes_claim=False)
 finally:
  await c.asyncTearDown();out['owned_runtime_removed']=not c.root.exists()
  (h.H/'title-notice-read-tests.json').write_text(json.dumps(out,indent=2),'utf8')
 print(json.dumps(out))
asyncio.run(main())
