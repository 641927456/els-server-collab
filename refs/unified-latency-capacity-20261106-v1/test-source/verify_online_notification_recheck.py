"""Positive preview/negative writer race reproducer and original output oracle."""
import runtime_fixture as h
import asyncio,contextlib,json,sqlite3,time
from unittest.mock import patch
from profile_town import seed
from els_server.domain.online_2026_clock import OnlineTitleClock
from els_server.domain import online_2026_campaign as original
def proposal(version):
 P=h.H/('experiments/online-notification-snapshot-v'+str(version))
 delivery=h.load('own_recheck_delivery'+str(version),P/'online_2026_delivery.py');display=h.load('own_recheck_display'+str(version),P/'online_2026_display.py');campaign=h.load('own_recheck_campaign'+str(version),P/'online_2026_campaign.py')
 campaign.OnlineTitleDelivery=delivery.OnlineTitleDelivery;campaign.OnlineTitleDisplay=display.OnlineTitleDisplay;return campaign
async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();outputs={};failures={}
 try:
  uid=seed(c,c.alice,'OwnRecheck',False);p=await c.peer(c.alice);await p.roster();await p.enter_town(uid);await c.server.periodics.close();s=c.app.playing[c.alice['id']];source=s.activity2026_awards.online.title;now=int(time.time())
  for label,module in [('original_frozen102',original),('proposal_v1',proposal(1)),('proposal_v2',proposal(2))]:
   path=c.root/(label+'.sqlite3')
   with contextlib.closing(sqlite3.connect(c.config.state_file))as a,contextlib.closing(sqlite3.connect(path))as b:a.backup(b)
   with contextlib.closing(sqlite3.connect(path))as db,db:
    db.execute('PRAGMA journal_mode=WAL');week,lo,hi=db.execute('SELECT week,starts,ends FROM online2026_periods WHERE campaign=?AND starts<=?AND ends>?',(source.clock.campaign,now,now)).fetchone();db.execute('DELETE FROM online2026_spans');db.execute('INSERT INTO online2026_spans VALUES(?,?,?,?,?,?,?,?)',(source.clock.campaign,c.alice['id'],uid,'own-ready',week,lo,lo+1800,99))
   identity=(str(path),c.alice['id'],uid,99);clock=OnlineTitleClock(source.clock.selection_bytes,campaign=source.clock.campaign,eligibility=lambda _:identity,monotonic=lambda:100.,epoch=lambda:float(now));clock.observe(s)
   flow=module.OnlineTitleCampaign(clock,title_link=source.link,record=source.record,enabled=lambda _:True,mail_identity=lambda _:identity,mail_policy=source.mail_policy,local_policy=module.LOCAL_POLICY)
   real=module.write_transaction;changed=[]
   @contextlib.contextmanager
   def recheck(db):
    # Only the synthetic private fixture changes between its two authority
    # reads; a positive preview never authorizes a grant by itself.
    with contextlib.closing(sqlite3.connect(path))as foreign,foreign:foreign.execute('DELETE FROM online2026_spans')
    changed.append(True)
    with real(db):yield db
   with patch.object(module,'write_transaction',recheck):
    try:events=flow.notifications(s)
    except RuntimeError as error:
     assert label=='proposal_v1'and str(error)=='Caller read snapshot required';failures[label]=str(error)
    else:
     with contextlib.closing(sqlite3.connect(path))as db:
      assert db.execute('SELECT COUNT(*) FROM online2026_delivery').fetchone()==(0,)
      outputs[label]=(events,tuple(sorted(db.iterdump())))
   assert changed==[True]
  assert failures=={'proposal_v1':'Caller read snapshot required'}
  assert outputs['original_frozen102']==outputs['proposal_v2']
 finally:await c.asyncTearDown()
 out=dict(passed=True,proposal_v1_bug_reproduced=True,proposal_v2_original_events_and_whole_SQL_equal=True,no_reward_issued_after_negative_recheck=True,owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections))
 (h.H/'online-notification-recheck-tests.json').write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
asyncio.run(main())
