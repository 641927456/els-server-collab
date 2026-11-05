"""Synthetic one-hour ledger, exact original snapshot and query-plan evidence."""
import runtime_fixture as h
import asyncio,contextlib,json,sqlite3,time
from els_server.storage.characters import Characters
from els_server.storage.online_2026_progress import OnlineTitleProgress as Original
from profile_town import seed
proposal=h.load('own_covering_progress',h.H/'experiments/online-span-covering-v2/online_2026_progress.py')
async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();results=[]
 try:
  uid=seed(c,c.alice,'OwnSpanIx',False);p=await c.peer(c.alice);await p.roster();await p.enter_town(uid);await c.server.periodics.close();s=c.app.playing[c.alice['id']];clock=s.activity2026_awards.online.title.clock;path=c.config.state_file
  identities=[(c.alice['id'],uid)]
  for n in range(1,25):
   account=c.app.registry.create('ownspanidx'+str(n));other=Characters(path,account['id']).create('OwnSpan'+str(n),1,'own-span-index-'+str(n))['uid'];identities.append((account['id'],other))
  with contextlib.closing(sqlite3.connect(path))as db,db:
   period=db.execute('SELECT week,starts,ends FROM online2026_periods WHERE campaign=? ORDER BY week LIMIT 1',(clock.campaign,)).fetchone();week,lo,hi=period;assert lo+3600<hi
   db.execute('UPDATE characters SET level=99 WHERE uid IN('+','.join('?'for _ in identities)+')',tuple(uid for _,uid in identities))
   db.execute('DELETE FROM online2026_spans')
   db.executemany('INSERT INTO online2026_spans VALUES(?,?,?,?,?,?,?,?)',((clock.campaign,account,character,'own-span:'+str(n),week,lo+n,lo+n+1,99)for account,character in identities for n in range(3600)))
  for label,klass in [('original',Original),('covering',proposal.OnlineTitleProgress)]:
   with contextlib.closing(sqlite3.connect(path))as db:
    repo=klass(db,clock.selection_bytes,campaign=clock.campaign)
    if label=='covering':
     before=db.execute('SELECT COUNT(*),SUM(ends-starts)FROM online2026_spans').fetchone()
     with db:db.execute('BEGIN IMMEDIATE');repo.initialize()
     assert db.execute('SELECT COUNT(*),SUM(ends-starts)FROM online2026_spans').fetchone()==before
    if label=='covering':
     assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='online2026_character_spans'").fetchone()
     schema=db.execute("SELECT name,sql FROM sqlite_master WHERE tbl_name='online2026_spans' ORDER BY name").fetchall()
     with db:db.execute('BEGIN IMMEDIATE');repo.initialize()
     assert db.execute("SELECT name,sql FROM sqlite_master WHERE tbl_name='online2026_spans' ORDER BY name").fetchall()==schema
    query='SELECT starts,ends FROM online2026_spans WHERE campaign=?AND character=?AND account=?AND week=?ORDER BY starts,ends';args=(clock.campaign,uid,c.alice['id'],week)
    plan=[r[3]for r in db.execute('EXPLAIN QUERY PLAN '+query,args)]
    steps=[0]
    def tick():steps[0]+=1000;return 0
    db.set_progress_handler(tick,1000);began=time.perf_counter();snapshots=[]
    for _ in range(10):snapshots.append(repo.snapshot(account=c.alice['id'],character=uid,week=week))
    elapsed=(time.perf_counter()-began)*1000;db.set_progress_handler(None,0)
    assert all(row==snapshots[0]for row in snapshots)and snapshots[0]['observed_online_seconds']==3600
    results.append(dict(label=label,query_plan=plan,SQLite_VM_steps_approximately=steps[0],ten_snapshots_ms=elapsed,snapshot=snapshots[0]))
  assert results[0]['snapshot']==results[1]['snapshot']
  assert any('COVERING INDEX online2026_character_account_spans'in p for p in results[1]['query_plan'])
  assert results[1]['SQLite_VM_steps_approximately']<results[0]['SQLite_VM_steps_approximately']
 finally:await c.asyncTearDown()
 out=dict(passed=True,proposal_only=True,synthetic_ledger_actors=25,synthetic_spans=90000,original_snapshot_equal=True,no_existing_row_mutations=True,all_actors_SQL_level99=True,only_one_progress_secondary_index=True,reinitialization_same_schema=True,rows=results,owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections))
 (h.H/'online-span-covering-v2-tests.json').write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
asyncio.run(main())
