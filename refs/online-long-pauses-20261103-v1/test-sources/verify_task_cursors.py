import source
from source import HERE,BASE
from pathlib import Path
import contextlib,datetime,hashlib,importlib.util,json,sqlite3,tempfile
from els_server.domain.attendance_2026 import AttendanceDefinition
from els_server.domain.attendance_2026_schedule import AttendanceSchedule
from els_server.domain.activity_2026_rewards import ActivityRewards
from els_server.storage.attendance_2026_progress import AttendanceProgress
from els_server.storage.attendance_2026_awards import AttendanceAwards,TASK_CARRY_POLICY
from els_server.storage.lifecycle import prepare_database
s=importlib.util.spec_from_file_location('parent_task_progress',BASE/'els_server/storage/attendance_2026_progress.py');parent=importlib.util.module_from_spec(s);s.loader.exec_module(parent)
raw=(BASE/'els_server/data/selected2026/attendance.json').read_bytes();definition=AttendanceDefinition.from_original(json.loads(raw));digest=hashlib.sha256(raw).hexdigest();catalog=ActivityRewards((BASE/'els_server/data/selected2026/rewards.json').read_bytes(),scope='attendance')
begin=int(datetime.datetime(2026,10,1,10,tzinfo=datetime.timezone(datetime.timedelta(hours=8))).timestamp());boundary=begin+86400
schedule=AttendanceSchedule.build(purpose='explicit_local_test',first_date=datetime.date(2026,10,1),available_from=begin,available_until=begin+42*86400)
def progress(cls,db):return cls(db,definition,campaign_id='owned-task-cursor',definition_sha256=digest)
def awards(p,policy):return AttendanceAwards(p,schedule,catalog,deadline=begin+43*86400,sender='owned',title='owned',body='owned',task_policy=policy)
def logical(db):return {r[0]:sorted(db.execute('SELECT * FROM '+r[0]).fetchall())for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
checks=[]
with tempfile.TemporaryDirectory(dir=HERE,prefix='owned-task-cursor-')as temp:
 for n,policy in enumerate((None,TASK_CARRY_POLICY)):
  pa=Path(temp)/f'parent{n}.sqlite3';pb=Path(temp)/f'indexed{n}.sqlite3';a=sqlite3.connect(pa);b=None
  try:
   a.execute('CREATE TABLE characters(uid INTEGER PRIMARY KEY,level INTEGER NOT NULL)');a.execute('INSERT INTO characters VALUES (1001,99)');a.execute('CREATE TABLE character_owners(uid INTEGER PRIMARY KEY,account_id INTEGER NOT NULL)');a.execute('INSERT INTO character_owners VALUES (1001,1)');a.commit()
   x=progress(parent.AttendanceProgress,a);x.initialize();schedule.install(x);t=awards(x,policy);t.initialize()
   oldperiod=schedule.periods[0].key;nextperiod=schedule.periods[1].key
   # A pre-acceptance history must remain excluded by the saved rowid floor.
   x.record_online(account='1',character='1001',level=99,period=oldperiod,operation='old-history',starts=begin,ends=begin+100)
   t.accept(account=1,character=1001,now=boundary-10)
   b=sqlite3.connect(pb);a.backup(b);b.close();b=None;prepare_database(pb);prepare_database(pb);b=sqlite3.connect(pb)
   y=progress(AttendanceProgress,b);u=awards(y,policy)
   assert logical(a)==logical(b)
   plan=b.execute('EXPLAIN QUERY PLAN SELECT period,payload,payload_sha256 FROM activity518_facts WHERE campaign=? AND account=? AND rowid>?',('owned-task-cursor','1',1)).fetchall();assert 'activity518_facts_account_cursor'in str(plan)and 'rowid>?'in str(plan)
   facts=[dict(period=oldperiod,operation='first',starts=boundary-9,ends=boundary-1),dict(period=oldperiod,operation='overlap',starts=boundary-8,ends=boundary-2),dict(period=nextperiod,operation='next-day',starts=boundary+2,ends=boundary+8),dict(period=nextperiod,operation='other-account',starts=boundary+2,ends=boundary+8,account='2'),dict(period=nextperiod,operation='low-level',starts=boundary+8,ends=boundary+10,level=9)]
   for fact in facts:
    args=dict(account='1',character='1001',level=99);args.update(fact)
    assert x.record_online(**args)==y.record_online(**args)
   assert t.snapshot(account=1,character=1001,now=boundary+10)==u.snapshot(account=1,character=1001,now=boundary+10)
   state=u.snapshot(account=1,character=1001,now=boundary+10);assert state['online_seconds']==(14 if policy else 8)
   assert not state['ready']and not state['reward_granted'];assert logical(a)==logical(b)
   checks.append(dict(policy=policy or 'original_daily',seconds=state['online_seconds'],old_history_excluded=True,overlap_not_doubled=True,other_account_and_low_level_excluded=True,cross_day_parent_equal=True))
   # Current carried tasks additionally attest every selected fact checksum.
   if policy:
    prior=[]
    for db,task in ((a,t),(b,u)):
     db.execute("UPDATE activity518_facts SET payload_sha256='owned-corrupt' WHERE operation='first'");db.commit();saved=logical(db)
     try:task.snapshot(account=1,character=1001,now=boundary+10)
     except ValueError as e:prior.append(str(e))
     else:raise AssertionError('Expected original checksum rejection')
     assert logical(db)==saved
    assert prior==['Attendance fact checksum changed']*2
    checks.append(dict(policy=policy,checksum_rejected_and_no_partial_task_update=True))
   for db in (a,b):
    assert db.execute('SELECT COUNT(*) FROM game_mail').fetchone()==(0,)
    assert db.execute('SELECT COUNT(*) FROM activity2026_reward_deliveries').fetchone()==(0,)
   assert logical(a)==logical(b)
  finally:
   a.close()
   if b is not None:b.close()
 # New install gets both exact query indexes without a startup migration.
 with sqlite3.connect(':memory:')as db:
  p=progress(AttendanceProgress,db);p.initialize();p.initialize()
  assert db.execute('PRAGMA index_info(activity518_facts_account_cursor)').fetchall()==[(0,0,'campaign'),(1,1,'account')]
  assert db.execute('PRAGMA index_info(activity518_facts_account_period)').fetchall()==[(0,0,'campaign'),(1,1,'account'),(2,3,'period')]
 checks.append(dict(first_install_both_indexes=True,repeat_initialize=True))
out=dict(passed=True,checks=checks,owned_runtime_removed=not Path(temp).exists(),mail_or_reward_issued=False,online_installed=False,sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in (HERE/'els_server/storage/lifecycle.py',HERE/'els_server/storage/attendance_2026_progress.py',HERE/'verify_tasks.py')})
(HERE/'task-results.json').write_text(json.dumps(out,indent=2),encoding='utf8');print(json.dumps(out))
