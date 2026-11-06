"""Pinned whole-SQL Master recovery oracle, negative reads and real rollback."""
import runtime_fixture as h
import contextlib,json,sqlite3,struct,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.game_data import client_data
from els_server.storage.game_schema import prepare
from els_server.storage.characters import Characters
from els_server.storage import master_presets as current
from els_server.storage.read_scope import committed_reads,ReadConnections

old=h.load('pinned_master_repair',h.BASE/'els_server/storage/master_presets.py')
def dump(path):
 with contextlib.closing(sqlite3.connect(path))as db:return tuple(db.iterdump())

results=[]
with tempfile.TemporaryDirectory(dir=h.H)as runtime:
 root=Path(runtime);base=root/'base.sqlite3';prepare(base)
 uid=Characters(base,1).create('OwnMaster',1,'own-master-normal-created-input')['uid']
 account=LocalAccount(LocalState(base,uid));account.enable_characters()
 for state in('ready','missing-table','pending','already-migrated','invalid-preset','trigger-failure'):
  replies=[];states=[];counts=[]
  for label,module in(('original',old),('candidate',current)):
   path=root/(state+'-'+label+'.sqlite3')
   with contextlib.closing(sqlite3.connect(base))as source,contextlib.closing(sqlite3.connect(path))as db:
    source.backup(db);db.execute('PRAGMA journal_mode=WAL')
    with db:
     if state=='missing-table':db.execute('DROP TABLE master_preset_migrations')
     if state in('pending','already-migrated','invalid-preset','trigger-failure'):
      assert db.execute('UPDATE characters SET unit_class=150,level=99,transcendence=1,master=1 WHERE uid=?',(uid,)).rowcount==1
      db.execute('UPDATE reward_balances SET experience=?WHERE uid=?',(client_data().thresholds[98],uid))
      payload=b'bad'if state=='invalid-preset'else struct.pack('>22i',21026,21217,*([0]*20))
      db.execute('INSERT OR REPLACE INTO skill_slots VALUES(?,?,0)',(uid,payload))
      if state=='already-migrated':db.execute('INSERT INTO master_preset_migrations VALUES(?,801001)',(uid,))
      if state=='trigger-failure':db.execute("CREATE TRIGGER own_master_failure BEFORE INSERT ON master_preset_migrations BEGIN SELECT RAISE(ABORT,'own migration failure');END")
   before=dump(path);queries=[];connect=sqlite3.connect
   def traced(*args,**kwargs):
    db=connect(*args,**kwargs);db.set_trace_callback(queries.append);return db
   with patch.object(sqlite3,'connect',traced):
    try:
     reply=(module.repair(path),module.repair(path))
     assert state not in('invalid-preset','trigger-failure'),'Invalid input did not reach real recovery'
     if state=='pending':assert reply==([uid],[])
    except (ValueError,sqlite3.IntegrityError)as error:
     reply=(type(error).__name__,str(error));assert dump(path)==before
   replies.append(reply);states.append(dump(path));counts.append(sum(q=='BEGIN IMMEDIATE'for q in queries))
   if label=='candidate'and state in('ready','already-migrated'):
    assert counts[-1]==0
    with contextlib.closing(connect(path,timeout=0))as blocker:
     blocker.execute('BEGIN IMMEDIATE');assert module.repair(path)==[];blocker.rollback()
   if label=='candidate'and state=='pending':
    # An explicitly removed choice is a later player choice, never repaired.
    with contextlib.closing(connect(path))as db,db:
     value=list(struct.unpack('>22i',db.execute('SELECT payload FROM skill_slots WHERE uid=?',(uid,)).fetchone()[0]));value[21]=0
     db.execute('UPDATE skill_slots SET payload=?WHERE uid=?',(struct.pack('>22i',*value),uid))
    assert module.repair(path)==[]
    with contextlib.closing(connect(path))as db:assert struct.unpack('>22i',db.execute('SELECT payload FROM skill_slots WHERE uid=?',(uid,)).fetchone()[0])[21]==0
  assert replies[0]==replies[1],(state,'Recovery result differs')
  assert states[0]==states[1],(state,'Recovery full SQL differs')
  results.append(dict(case=state,writer_begins=dict(zip(('original','candidate'),counts)),result_and_entire_SQL_equal=True))
 # The old unit fixture assumes an automatically created UID1001; that actor
 # no longer exists in the unified server. Use an actually created role.
 path=root/'pending-candidate.sqlite3'
 reopened=LocalAccount(LocalState(path,uid));reopened.enable_characters()
 assert reopened.master_preset_repair==[] and reopened.get_skills()[21]==0
out=dict(passed=True,pinned_recovery_cases=results,negative_recovers_under_real_WAL_writer=True,failed_partial_repair_rolls_back=True,later_empty_master_choice_preserved=True,normal_created_role_and_actual_reopened_account=True,historical_UID1001_fixture_invalid_on_pinned_v5_and_candidate=True,owned_runtime_removed=not root.exists())
(h.H/'master-repair-read-tests.json').write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
