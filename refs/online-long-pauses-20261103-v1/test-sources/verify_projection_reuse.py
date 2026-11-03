import source
from source import HERE,BASE
from pathlib import Path
import contextlib,hashlib,importlib.util,json,sqlite3,tempfile,time
from els_server.domain import selected_2026_pair_runtime as factory
from els_server.domain import attendance_online_2026 as candidate
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage.attendance_2026_progress import AttendanceProgress
from els_server.storage.read_scope import committed_reads
spec=importlib.util.spec_from_file_location('original_online_projection',BASE/'els_server/domain/attendance_online_2026.py');original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
pack=json.loads((BASE/'els_server/data/selected2026/local-pair.json').read_bytes());configuration=pack['configuration'];resources={k:(BASE/'els_server/data/selected2026'/v['file']).read_bytes()for k,v in pack['resources'].items()};ticks=[float(configuration['attendance']['starts']+200),0.]
def manager(path):
 m=factory.SelectedAttendanceOnline(path,configuration,resources,epoch=lambda:ticks[0],monotonic=lambda:ticks[1]);m.install();return m
def session(path):
 account=LocalAccount(LocalState(path));account.enable_characters()
 s=LocalSession(account,enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True);s.role='game';s.phase='town_ready';s.completed.update((0x28,0x225,0x227));return s
def logical(path):
 with contextlib.closing(sqlite3.connect(path))as db:return {r[0]:sorted(db.execute('SELECT * FROM '+r[0]).fetchall())for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
checks=[];bench={}
with tempfile.TemporaryDirectory(dir=HERE,prefix='owned-projection-reuse-')as temp:
 paths=[Path(temp)/'parent.sqlite3',Path(temp)/'candidate.sqlite3'];s1=session(paths[0]);m1=manager(paths[0])
 with contextlib.closing(sqlite3.connect(paths[0]))as db,db:db.execute('UPDATE characters SET level=99 WHERE uid=?',(s1.account.uid,))
 m1.settings.update(dict(operation_id='00000000-0000-0000-0000-000000000001',reason='owned projection reuse',expected_revision=0,enabled=dict(attendance=True,online=True,growth=False)));m1.state=m1.settings.snapshot()
 with contextlib.closing(sqlite3.connect(paths[0]))as a,contextlib.closing(sqlite3.connect(paths[1]))as b:a.backup(b)
 s2=session(paths[1]);m2=manager(paths[1]);sessions=[s1,s2];managers=[m1,m2];flows=[];counts=[0,0]
 for n,(m,s,cls)in enumerate(zip(managers,sessions,(original.AttendanceOnlineCampaign,candidate.AttendanceOnlineCampaign))):
  factory.AttendanceOnlineCampaign=cls;flow=m(s.account);flows.append(flow);s.activity2026_awards=flow;real=flow._projection
  def projection(s,n=n,real=real):counts[n]+=1;return real(s)
  flow._projection=projection
 factory.AttendanceOnlineCampaign=candidate.AttendanceOnlineCampaign
 def compare(name,expected_calls):
  counts[:]=[0,0];out=[]
  for s,f in zip(sessions,flows):
   with committed_reads():out.append(f.finalize(s,[]))
  assert out[0]==out[1],(name,[[(e.kind,e.payload.hex()[:80])for e in r]for r in out])
  assert counts==expected_calls,(name,counts)
  assert logical(paths[0])==logical(paths[1]),name
  checks.append(dict(test=name,projection_calls=list(counts),packets_equal=True,logical_rows_equal=True,accepted_notices=sum(e.kind==0xf0 for e in out[0])))
  return out
 first=compare('first_town_entry_registers_same_original_F0_once',[2,1]);assert sum(e.kind==0xf0 for e in first[0])==1
 repeated=compare('already_registered_task_does_not_repeat_F0',[2,1]);assert not any(e.kind==0xf0 for e in repeated[0])
 # Pending, overlapping observed intervals exercise the expensive real ledger.
 period=m1.schedule.period_at(int(ticks[0]));start=int(ticks[0]);ticks[0]+=400
 for path,m in zip(paths,managers):
  with contextlib.closing(sqlite3.connect(path))as db:
   p=AttendanceProgress(db,m.definition,campaign_id=m.config['attendance']['campaign'],definition_sha256=m.digest)
   p.record_online(account='1',character=str(s1.account.uid),level=99,period=period,operation='owned-observed-interval',starts=start,ends=start+200)
 compare('current_observed_progress_remains_byte_identical',[2,1])
 for s in sessions:s.phase='dungeon_active'
 compare('dungeon_branch_keeps_its_existing_single_projection',[1,1])
 for s in sessions:s.phase='town_ready'
 compare('same_role_town_return_preserves_registration_generation',[2,1])
 # A different selected role on the same account needs its own wire owner.
 for n,(path,s)in enumerate(zip(paths,sessions)):
  uid=s.account.characters.create('OwnedRoleTwo',5,'owned-same-second-role')['uid'];s.account=s.account.for_character(uid)
  with contextlib.closing(sqlite3.connect(path))as db,db:db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,))
 compare('selected_role_change_uses_current_UID_in_original_notice',[2,1])
 # Below-level and inactive periods must not borrow the previous role's view.
 for path,s in zip(paths,sessions):
  with contextlib.closing(sqlite3.connect(path))as db,db:db.execute('UPDATE characters SET level=9 WHERE uid=?',(s.account.uid,))
 compare('low_level_role_does_not_reuse_a_prior_eligible_view',[0,0])
 for path,s in zip(paths,sessions):
  with contextlib.closing(sqlite3.connect(path))as db,db:db.execute('UPDATE characters SET level=99 WHERE uid=?',(s.account.uid,))
 for m in managers:m.state['enabled']['attendance']=False
 compare('disabled_campaign_keeps_original_no_projection_path',[0,0])
 for m in managers:m.state['enabled']['attendance']=True
 # Existing writer contention follows the original read-only committed view.
 held=[sqlite3.connect(p)for p in paths]
 try:
  for db in held:db.execute('BEGIN IMMEDIATE')
  counts[:]=[0,0];out=[f.finalize(s,[])for f,s in zip(flows,sessions)];assert out[0]==out[1]and counts==[2,1]
 finally:
  for db in held:db.rollback();db.close()
 checks.append(dict(test='busy_writer_keeps_original_readonly_fallback_packets',projection_calls=list(counts),packets_equal=True))
 # Larger pending source uses valid overlapping facts below the 3600s gate.
 for path,m,s in zip(paths,managers,sessions):
  with contextlib.closing(sqlite3.connect(path))as db,db:
   rows=[]
   for i in range(4000):
    fact=dict(kind='online',starts=start,ends=start+200,qualifies=True,character=str(s.account.uid),level=99,period=period);raw=json.dumps(fact,sort_keys=True,separators=(',',':'));rows.append((m.config['attendance']['campaign'],'1','owned-overlap-'+str(i),period,raw,hashlib.sha256(raw.encode()).hexdigest()))
   db.executemany('INSERT INTO activity518_facts VALUES (?,?,?,?,?,?)',rows)
 for n,(f,s)in enumerate(zip(flows,sessions)):
  counts[n]=0;before=time.perf_counter();out=f.finalize(s,[]);bench['parent'if n==0 else'candidate']=dict(ms=(time.perf_counter()-before)*1000,projection_calls=counts[n],events=out)
 assert bench['parent'].pop('events')==bench['candidate'].pop('events')
 assert bench['parent']['projection_calls']==2 and bench['candidate']['projection_calls']==1
 assert logical(paths[0])==logical(paths[1])
out=dict(passed=True,checks=checks,pending_4000_facts_benchmark=bench,owned_runtime_removed=not Path(temp).exists(),online_installed=False,sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in(HERE/'els_server/domain/attendance_online_2026.py',HERE/'verify_projection_reuse.py',BASE/'els_server/domain/attendance_2026_award_flow.py')})
(HERE/'projection-reuse-results.json').write_text(json.dumps(out,indent=2),encoding='utf8');print(json.dumps(out))
