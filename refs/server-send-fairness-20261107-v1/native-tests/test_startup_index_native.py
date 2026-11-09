"""Actual startup prepares an existing source index without touching reward rows."""
import bootstrap,runtime_fixture as h
import asyncio,contextlib,json,psutil,sqlite3,sys,time,traceback
from els_server.application import Application
from els_server.storage.characters import Characters
from els_server.storage.achievement_history import counts
from els_server.__main__ import _native_timing,_normal_scheduling
psutil.Process().cpu_affinity([20,22]);_normal_scheduling()
INDEX='native_achievement_clear_owner_dungeon'
async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();out=dict(ok=False,checks={},source_preview=True,online_capacity_claim=False)
 try:
  path=c.config.state_file;account=c.alice['id'];uid=Characters(path,account).create('OwnIndex',1,'owned-startup-index-role')['uid']
  with contextlib.closing(sqlite3.connect(path))as db,db:
   assert db.execute('SELECT 1 FROM sqlite_master WHERE name=?',(INDEX,)).fetchone()==(1,)
   db.execute('DROP INDEX '+INDEX)
   db.executemany('INSERT INTO reward_receipts VALUES(?,?,?,?,?)',[(f'owned-source-index-{n}','a'*64,json.dumps(dict(owner=uid,dungeon_clear=[34350,1]))if n%3==0 else json.dumps(dict(owner=uid,ed=0,experience=0)),b'owned-fixture','{}')for n in range(12000)])
  with contextlib.closing(sqlite3.connect(path))as db:
   before=tuple(db.execute('SELECT COUNT(*),SUM(length(grant_json)),SUM(length(response))FROM reward_receipts').fetchone())
   started=time.perf_counter();expected=counts(db,account,{49});out['unindexed_count_ms']=(time.perf_counter()-started)*1000
  await c.server.close();c.app.close()
  app=Application(c.config);c.app=app;started=time.perf_counter();await app.start();out['full_startup_ms']=(time.perf_counter()-started)*1000
  assert not app.playing and not app.accounts
  with contextlib.closing(sqlite3.connect(path))as db:
   assert db.execute('SELECT 1 FROM sqlite_master WHERE name=?',(INDEX,)).fetchone()==(1,)
   after=tuple(db.execute('SELECT COUNT(*),SUM(length(grant_json)),SUM(length(response))FROM reward_receipts').fetchone());assert after==before
   started=time.perf_counter();actual=counts(db,account,{49});out['indexed_count_ms']=(time.perf_counter()-started)*1000
   assert actual==expected and actual[(49,34350)]==4000
   sql="SELECT json_extract(a.grant_json,'$.dungeon_clear[0]'),COUNT(*) FROM reward_receipts a WHERE COALESCE(json_extract(a.grant_json,'$.owner'),1001)IN (SELECT +uid FROM character_owners WHERE account_id=?) AND json_type(a.grant_json,'$.dungeon_clear')='array' GROUP BY json_extract(a.grant_json,'$.dungeon_clear[0]')"
   plan=[row[-1]for row in db.execute('EXPLAIN QUERY PLAN '+sql,(account,))];assert any(INDEX in row for row in plan);out['query_plan']=plan
  out['checks'].update(index_ready_before_any_player_or_listener=True,restart_prepares_index_on_existing_history=True,reward_receipts_unchanged=True,original_account_scoped_counts_equal=True,existing_expression_index_is_used=True)
  out['ok']=True
 except BaseException as error:out.update(error=repr(error),traceback=traceback.format_exc())
 finally:
  await c.asyncTearDown();out.update(owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections),
   errors=[r['event']for r in c.events if r['event']in('worker_error','notification_error','connection_task_error')],source=bootstrap.SOURCE_BINDINGS,GIL_enabled=sys._is_gil_enabled())
  out['ok']=out['ok']and out['owned_runtime_removed']and out['connections']==0 and not out['errors']
  target=bootstrap.HERE/'notebook-evidence';target.mkdir(exist_ok=True);(target/'native-startup-index.json').write_text(json.dumps(out,indent=2),'utf8')
 print(json.dumps({k:v for k,v in out.items()if k!='source'}));return out['ok']
if __name__=='__main__':
 with _native_timing():raise SystemExit(not asyncio.run(main()))
