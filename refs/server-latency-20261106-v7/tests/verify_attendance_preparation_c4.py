"""Real selected calendar/catalog, own SQLite only; no player or cloud access."""
import bootstrap as h
import contextlib,hashlib,json,sqlite3,sys,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from els_server.domain.selected_2026_pair_runtime import SelectedAttendanceOnline
from els_server.domain.attendance_2026_award_flow import AttendanceAwardFlow
from els_server.storage.attendance_2026_awards import AttendanceAwards
from els_server.storage.attendance_2026_tasks import AttendanceTasks
from els_server.storage import attendance_2026_progress as progress_module
from els_server.storage.sqlite_timing import begin_write,commit_write,end_write

class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=h.HERE);self.addCleanup(self.tmp.cleanup)
  self.path=Path(self.tmp.name)/'own.sqlite3'
  directory=h.BASE/'els_server/data/selected2026';pack=json.loads((directory/'local-pair.json').read_bytes())
  self.manager=SelectedAttendanceOnline(self.path,pack['configuration'],{k:(directory/v['file']).read_bytes()for k,v in pack['resources'].items()})
  self.manager.catalog.register_inventory()
  self.db=sqlite3.connect(self.path);self.addCleanup(self.db.close)
  self.db.executescript('''PRAGMA journal_mode=WAL;PRAGMA synchronous=FULL;
   CREATE TABLE characters(uid INTEGER PRIMARY KEY,level INTEGER);
   CREATE TABLE character_owners(uid INTEGER PRIMARY KEY,account_id INTEGER);
   CREATE TABLE reward_balances(uid INTEGER PRIMARY KEY,ed INTEGER,experience INTEGER,revision INTEGER);
   CREATE TABLE inventory_sequence(id INTEGER PRIMARY KEY,next_uid INTEGER);
   CREATE TABLE inventory_items(uid INTEGER PRIMARY KEY);
   CREATE TABLE own_probe(value INTEGER);
   INSERT INTO characters VALUES(1001,99);INSERT INTO character_owners VALUES(1001,1);
   INSERT INTO reward_balances VALUES(1001,100,0,1);INSERT INTO inventory_sequence VALUES(1,50001);''')
  self.t=self.manager._attendance(self.db);self.t.progress.initialize();self.manager.schedule.install(self.t.progress);self.t.initialize()
  periods=self.manager.schedule.periods;self.accepted=periods[14].ends-100;self.now=periods[15].starts+500
  self.t.accept(account=1,character=1001,now=self.accepted)
  a=self.manager.config['attendance']
  self.flow=AttendanceAwardFlow(self.manager.definition,campaign=a['campaign'],definition_sha256=self.manager.digest,schedule=self.manager.schedule,clock=lambda:self.now,catalog=self.manager.catalog,anchor_value=a['starts'],other_reward_rows={},purchase_policy=self.t.purchase_policy,task_policy=self.t.task_policy,**a['mail'])
  self.s=SimpleNamespace(account=SimpleNamespace(uid=1001,account_id=1,store=SimpleNamespace(path=self.path)))
 def fact(self,t=None,*,account='1',operation='own-online',start=None,end=None):
  t=t or self.t;start=self.manager.schedule.periods[15].starts if start is None else start;end=start+100 if end is None else end
  period=t.schedule.period_at(start)
  return t.progress.record_online(account=account,period=period,operation=operation,character='1001',level=99,starts=start,ends=end)
 def counters(self):
  with contextlib.closing(sqlite3.connect(self.path))as db:return db.execute('SELECT clears,seconds,ready_at FROM activity518_tasks').fetchone()
 def inject_before_writer(self,action):
  original=self.flow._store;calls=[]
  def store(db):
   calls.append(1)
   if len(calls)==2:action()
   return original(db)
  return patch.object(self.flow,'_store',store)
 def test_carry_and_overlapping_intervals_match_original_refresh(self):
  self.fact(start=self.accepted,end=self.accepted+90,operation='first-day')
  self.fact();self.fact(start=self.manager.schedule.periods[15].starts+50,end=self.manager.schedule.periods[15].starts+150,operation='overlap')
  prepared=self.t._refresh(1,self.now,persist=False);self.assertEqual(prepared['online_seconds'],240)
  self.assertEqual(self.counters(),(0,0,None))
  actual=self.flow._projection(self.s)[0];self.assertEqual(actual,prepared);self.assertEqual(self.counters(),(0,240,None))
  original_path=h.BASE/'els_server/storage/attendance_2026_awards.py'
  # Compile the unmodified class method as an oracle; carry method has no super call.
  import ast
  tree=ast.parse(original_path.read_bytes());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name=='AttendanceAwards')
  fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef)and n.name=='_refresh')
  namespace=dict(hashlib=hashlib,json=json);exec(compile(ast.Module(body=[fn],type_ignores=[]),'pinned-original-refresh','exec'),namespace)
  with self.t._transaction():expected=namespace['_refresh'](self.t,1,self.now)
  self.assertEqual(actual,expected)
 def test_no_change_ready_and_absent_never_acquire_writer(self):
  def unexpected(*a,**kw):raise AssertionError('No-op projection acquired writer')
  with patch.object(progress_module,'begin_write',unexpected):self.assertEqual(self.flow._projection(self.s)[0]['online_seconds'],0)
  with self.db:self.db.execute('UPDATE activity518_tasks SET seconds=3600,ready_at=?',(self.now,))
  with patch.object(progress_module,'begin_write',unexpected):self.assertTrue(self.flow._projection(self.s)[0]['ready'])
  with self.db:self.db.execute('DELETE FROM activity518_tasks')
  with patch.object(progress_module,'begin_write',unexpected):self.assertIsNone(self.flow._projection(self.s)[0])
 def test_append_in_later_period_does_not_overwrite_committed_view(self):
  self.fact()
  with self.inject_before_writer(lambda:self.fact(operation='appended',start=self.manager.schedule.periods[15].starts+100,end=self.manager.schedule.periods[15].starts+200)):
   self.assertEqual(self.flow._projection(self.s)[0]['online_seconds'],0)
  self.assertEqual(self.counters(),(0,0,None));self.assertEqual(self.flow._projection(self.s)[0]['online_seconds'],200)
 def test_same_second_reaccept_is_not_old_prepared_task(self):
  self.fact()
  def reaccept():
   with self.db:
    floor=self.db.execute('SELECT max(rowid) FROM activity518_facts').fetchone()[0]
    self.db.execute('DELETE FROM activity518_tasks')
    self.db.execute('INSERT INTO activity518_tasks(campaign,account,accepted_period,accepted_at,fact_floor) VALUES(?,?,?,?,?)',(self.t.progress.campaign,1,self.manager.schedule.period_at(self.accepted),self.accepted,floor))
  with self.inject_before_writer(reaccept):self.assertEqual(self.flow._projection(self.s)[0]['online_seconds'],0)
  self.assertEqual(self.counters(),(0,0,None))
 def test_other_accounts_append_does_not_defer_this_task(self):
  self.fact()
  with self.inject_before_writer(lambda:self.fact(account='2',operation='unrelated')):
   self.assertEqual(self.flow._projection(self.s)[0]['online_seconds'],100)
 def test_owner_or_path_changes_are_rejected(self):
  self.fact();original=self.s.account
  with self.inject_before_writer(lambda:setattr(self.s,'account',SimpleNamespace(uid=1002,account_id=2,store=original.store))):
   with self.assertRaisesRegex(ValueError,'selected owner changed'):self.flow._projection(self.s)
  self.s.account=original
  with self.inject_before_writer(lambda:setattr(original.store,'path',Path(self.tmp.name)/'other.sqlite3')):
   with self.assertRaises(FileNotFoundError):self.flow._projection(self.s)
  original.store.path=self.path;self.assertEqual(self.counters(),(0,0,None))
 def test_prepare_is_read_only_and_does_not_hold_sql_writer(self):
  self.fact();entered=threading.Event();release=threading.Event();output=[];errors=[];refresh=AttendanceAwards._refresh
  def held(t,*a,**kw):
   out=refresh(t,*a,**kw)
   if kw.get('persist')is False:entered.set();self.assertTrue(release.wait(5))
   return out
  def project():
   try:output.append(self.flow._projection(self.s))
   except BaseException as e:errors.append(e)
  with patch.object(AttendanceAwards,'_refresh',held):
   worker=threading.Thread(target=project);worker.start()
   try:
    self.assertTrue(entered.wait(5))
    with contextlib.closing(sqlite3.connect(self.path,timeout=0))as db:
     acquired=begin_write(db)
     try:db.execute('INSERT INTO own_probe VALUES(1)');commit_write(db)
     finally:end_write(acquired)
    self.assertEqual(self.counters(),(0,0,None))
   finally:release.set();worker.join(5)
  self.assertFalse(worker.is_alive());self.assertEqual(errors,[]);self.assertEqual(output[0][0]['online_seconds'],100)
 def test_physical_commit_failure_does_not_publish_prepared_counters(self):
  self.fact()
  with patch.object(progress_module,'commit_write',side_effect=sqlite3.OperationalError('owned commit I/O failure')):
   with self.assertRaisesRegex(sqlite3.OperationalError,'commit I/O failure'):self.flow._projection(self.s)
  self.assertEqual(self.counters(),(0,0,None))
 def test_ready_claim_rollback_replay_and_cold_mail(self):
  self.fact(start=self.manager.schedule.periods[15].starts,end=self.manager.schedule.periods[15].starts+3600);self.now+=3600
  self.assertTrue(self.flow._projection(self.s)[0]['ready'])
  before=list(self.db.iterdump())
  def fail(out):raise ValueError('owned encode failure')
  with self.assertRaisesRegex(ValueError,'encode failure'):self.t.claim(account=1,character=1001,now=self.now,operation='own-claim',encode=fail)
  self.assertEqual(list(self.db.iterdump()),before)
  result=self.t.claim(account=1,character=1001,now=self.now,operation='own-claim',encode=lambda out:b'OK')
  self.assertFalse(result['replayed']);again=self.t.claim(account=1,character=1001,now=self.now,operation='own-claim',encode=lambda out:b'OK')
  self.assertTrue(again['replayed']);self.assertEqual(result['mail_id'],again['mail_id'])
  with contextlib.closing(sqlite3.connect(self.path))as cold:
   for table in('activity518_stamps','activity2026_reward_deliveries','game_mail','player_mail_items'):
    self.assertEqual(cold.execute('SELECT count(*) FROM '+table).fetchone()[0],1)
 def test_noncarry_refresh_remains_accepted_period_only(self):
  self.fact();self.flow.task_policy=None
  projected=self.flow._projection(self.s)[0]
  self.assertEqual(projected['online_seconds'],0);self.assertTrue(projected['incomplete_carry_rule_pending'])
  base=AttendanceTasks(self.t.progress,self.t.schedule)
  with base._transaction():expected=base._refresh(1,self.now)
  self.assertEqual(projected,expected)
 def test_registered_rewards_serialize_and_retained_boxes_keep_authority(self):
  from els_server.storage.mail_attachments import _snapshot
  from els_server.domain import inventory_items as items
  from els_server.domain.potion_choice_box import read_existing
  for rid in range(8127,8169):
   for row in self.manager.catalog.plan(rid):
    item=dict(uid=50001,template=row['template'],metadata=row['metadata'],group=row['group'],slot=0,count=row['quantity'])
    self.assertEqual(json.loads(_snapshot(item)),item)
  retained=dict(uid=50002,template=718113,metadata=0,group=4,slot=0,count=1)
  with patch.dict(items.VERIFIED_TEMPLATES,clear=False):
   items.VERIFIED_TEMPLATES.pop(718113,None)
   with self.assertRaisesRegex(ValueError,'unchanged SQL reader'):items.validate_item(retained)
   owned=read_existing(retained);self.assertEqual(items.validate_item(owned),retained)
   owned['count']+=1
   with self.assertRaisesRegex(ValueError,'unchanged SQL reader'):items.validate_item(owned)
  approved=dict(uid=50003,template=716611,metadata=0,group=4,slot=0,count=1)
  self.assertEqual(items.validate_item(approved),approved)
  for change in(dict(metadata=2),dict(group=6),dict(count=0),dict(slot=-1)):
   with self.assertRaises(ValueError):items.validate_item(dict(approved,**change))

if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(Tests);result=unittest.TextTestRunner(verbosity=2).run(suite)
 report=dict(passed=result.wasSuccessful(),tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),runtime=sys.version,GIL_enabled=sys._is_gil_enabled(),source=h.SOURCE_BINDINGS,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),production_access=False)
 (h.HERE/'attendance-preparation-tests.json').write_text(json.dumps(report,indent=2),'utf8')
 sys.exit(0 if result.wasSuccessful()else 1)
