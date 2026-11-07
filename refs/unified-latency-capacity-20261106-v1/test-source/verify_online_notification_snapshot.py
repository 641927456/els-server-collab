"""Fresh native identity, original wire/SQL oracle and one history scan."""
import runtime_fixture as h
import asyncio,contextlib,copy,importlib,json,sqlite3,time
from unittest.mock import patch
from profile_town import seed
from els_server.domain.online_2026_clock import OnlineTitleClock
from els_server.domain import online_2026_campaign as old
P=h.H/'experiments/online-notification-snapshot-v1'
delivery=h.load('own_notification_delivery',P/'online_2026_delivery.py')
display=h.load('own_notification_display',P/'online_2026_display.py')
new=h.load('own_notification_campaign',P/'online_2026_campaign.py')
new.OnlineTitleDelivery=delivery.OnlineTitleDelivery;new.OnlineTitleDisplay=display.OnlineTitleDisplay
old_display=importlib.import_module('els_server.domain.online_2026_display')
baseline=h.load('own_original_online_campaign',h.BASE/'els_server/domain/online_2026_campaign.py')
def contents(path):
 with contextlib.closing(sqlite3.connect(path))as db:return tuple(sorted(db.iterdump()))
async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();checks=[]
 try:
  uid=seed(c,c.alice,'OwnNotRead',False);p=await c.peer(c.alice);await p.roster();await p.enter_town(uid);await c.server.periodics.close()
  s=c.app.playing[c.alice['id']];source=s.activity2026_awards.online.title;now=int(time.time());connect=sqlite3.connect
  def create(label,module,seconds,level=99):
   path=c.root/(label+'.sqlite3')
   with contextlib.closing(connect(c.config.state_file))as a,contextlib.closing(connect(path))as b:a.backup(b)
   with contextlib.closing(connect(path))as db,db:
    db.execute('PRAGMA journal_mode=WAL');db.execute('UPDATE characters SET level=? WHERE uid=?',(level,uid))
    week,lo,hi=db.execute('SELECT week,starts,ends FROM online2026_periods WHERE campaign=?AND starts<=?AND ends>?',(source.clock.campaign,now,now)).fetchone()
    assert lo+seconds<hi;db.execute('DELETE FROM online2026_spans')
    db.executemany('INSERT INTO online2026_spans VALUES(?,?,?,?,?,?,?,?)',((source.clock.campaign,c.alice['id'],uid,'own-history:'+str(n),week,lo+n,lo+n+1,99)for n in range(seconds)))
   identity=(str(path),c.alice['id'],uid,99)
   clock=OnlineTitleClock(source.clock.selection_bytes,campaign=source.clock.campaign,eligibility=lambda _:identity,monotonic=lambda:100.,epoch=lambda:float(now));clock.observe(s)
   flow=module.OnlineTitleCampaign(clock,title_link=source.link,record=source.record,enabled=lambda _:True,mail_identity=lambda _:identity,mail_policy=source.mail_policy,local_policy=module.LOCAL_POLICY)
   return path,flow
  for case,seconds,level in [('empty',0,99),('half',900,99),('ready',1800,99),('ineligible',900,9)]:
   outputs={};traces={}
   for label,module in [('original',old),('proposal',new)]:
    path,flow=create(case+'-'+label,module,seconds,level);queries=[];before=contents(path)
    def traced(*args,**kwargs):db=connect(*args,**kwargs);db.set_trace_callback(queries.append);return db
    with patch.object(sqlite3,'connect',traced):events=flow.notifications(s)
    after=contents(path)
    if case!='ready':assert before==after
    history=sum('SELECT STARTS,ENDS FROM ONLINE2026_SPANS'in ' '.join(q.upper().split())for q in queries)
    traces[label]=history
    if case in('empty','half'):assert history==(2 if label=='original'else 1),(case,label,history)
    flow._force=True
    with patch.object(sqlite3,'connect',traced):repeat=flow.notifications(s)
    assert contents(path)==after,'Notification replay changed SQL'
    outputs[label]=(events,repeat,after)
   assert outputs['original']==outputs['proposal'],case
   checks.append(dict(case=case,events_and_whole_SQL_equal=True,history_queries=traces))
  for label,module,encoder_module in [('original',old,old_display),('proposal',new,display)]:
   path,flow=create('encoding-'+label,module,900);before=contents(path);state=copy.copy(vars(flow.display));scan=(flow._context,flow._next_scan,flow._force)
   def reject(*args,**kwargs):raise ValueError('Owned notification encoder failure')
   with patch.object(encoder_module,'activity_list_update',reject):
    try:flow.notifications(s)
    except ValueError as error:assert str(error)=='Owned notification encoder failure'
    else:raise AssertionError('Notification encoding failure hidden')
   assert contents(path)==before and vars(flow.display)==state and(flow._context,flow._next_scan,flow._force)==scan
   flow.notifications(s)
   path,flow=create('owner-'+label,module,900)
   with contextlib.closing(connect(path))as db,db:db.execute('UPDATE character_owners SET account_id=account_id+100 WHERE uid=?',(uid,))
   before=contents(path)
   try:flow.notifications(s)
   except ValueError:pass
   else:raise AssertionError('Changed SQL owner accepted')
   assert contents(path)==before
  checks.extend(['encoding failure leaves projection/scan/SQL unchanged and retry succeeds','fresh changed owner refused by both'])
  for label,module in [('original_release',baseline),('proposal',new)]:
   path,flow=create('busy-'+label,module,900)
   with contextlib.closing(connect(path))as db:assert db.execute('PRAGMA journal_mode=DELETE').fetchone()==('delete',)
   before=contents(path);projection=copy.copy(vars(flow.display));scan=(flow._context,flow._next_scan,flow._force)
   with contextlib.closing(connect(path,timeout=0))as blocker:
    blocker.execute('BEGIN EXCLUSIVE');began=time.perf_counter();events=flow.notifications(s);elapsed=(time.perf_counter()-began)*1000
    assert not events and elapsed<200,(label,elapsed)
    assert vars(flow.display)==projection and(flow._context,flow._next_scan,flow._force)==scan
    blocker.rollback()
   assert contents(path)==before
   checks.append(dict(case='exclusive_lock_immediate_deferral',label=label,elapsed_ms=elapsed,projection_and_SQL_unchanged=True))
 finally:await c.asyncTearDown()
 out=dict(passed=True,proposal_only=True,production_installed=False,checks=checks,owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections))
 (h.H/'online-notification-snapshot-tests.json').write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
asyncio.run(main())
