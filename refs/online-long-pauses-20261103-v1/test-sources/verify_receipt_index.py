import source
from source import HERE,BASE
import contextlib,hashlib,importlib.util,json,sqlite3,tempfile,time,unittest
from els_server.storage.lifecycle import prepare_database
from els_server.domain.cartridge_registration_rules import read_account

spec=importlib.util.spec_from_file_location('existing_inventory_actions','G:/els/tests/test_inventory_actions.py')
tests=importlib.util.module_from_spec(spec);spec.loader.exec_module(tests)
INDEX='inventory_action_receipts_kind_owner'
DDL='''CREATE TABLE inventory_action_receipts (
 operation_id TEXT PRIMARY KEY,request_hash TEXT NOT NULL,owner INTEGER NOT NULL,
 kind INTEGER NOT NULL,positions_json TEXT NOT NULL,before_json TEXT NOT NULL,after_json TEXT NOT NULL)'''

def outcome(db,account):
 db.execute('BEGIN')
 try:
  try:return dict(value=read_account(db,account))
  except ValueError as e:return dict(error=str(e))
 finally:db.rollback()

def measured(db):
 steps=[0];db.set_progress_handler(lambda:steps.__setitem__(0,steps[0]+100)or 0,100)
 started=time.perf_counter();value=outcome(db,1);elapsed=(time.perf_counter()-started)*1000
 db.set_progress_handler(None,0)
 return dict(milliseconds=elapsed,vm_steps=steps[0],value=value)

report={}
with tempfile.TemporaryDirectory(dir=HERE,prefix='owned-index-')as temp:
 path=source.Path(temp)/'old.sqlite3'
 with contextlib.closing(sqlite3.connect(path))as db,db:
  db.execute('CREATE TABLE character_owners(uid INTEGER PRIMARY KEY,account_id INTEGER NOT NULL)')
  db.execute('CREATE INDEX character_owners_account ON character_owners(account_id)')
  db.executemany('INSERT INTO character_owners VALUES (?,?)',[(1001,1),(1002,2)])
  db.execute(DDL)
  wide='["'+('x'*8192)+'"]'
  db.executemany('INSERT INTO inventory_action_receipts VALUES (?,?,?,?,?,?,?)',
   ((str(i),'hash',1001+i%2,0x109,'[]',wide,'[]')for i in range(8921)))
 with contextlib.closing(sqlite3.connect(path))as db:
  before=measured(db)
  # These three corruption/rejection outcomes must survive the upgrade exactly.
  cases={}
  for kind in (0xd4e,0xd50,0xd52,0xd54):
   db.execute('INSERT INTO inventory_action_receipts VALUES (?,?,?,?,?,?,?)',('owned-bad','hash',1001,kind,'[]','[]','[]'));db.commit()
   cases[kind]=outcome(db,1);assert 'error'in cases[kind]
   assert outcome(db,2)==before['value']
   db.execute("DELETE FROM inventory_action_receipts WHERE operation_id='owned-bad'");db.commit()
  saved=db.execute('SELECT * FROM inventory_action_receipts ORDER BY operation_id').fetchall()
 prepare_database(path);prepare_database(path)
 with contextlib.closing(sqlite3.connect(path))as db:
  assert db.execute('SELECT * FROM inventory_action_receipts ORDER BY operation_id').fetchall()==saved
  assert db.execute('PRAGMA index_info('+INDEX+')').fetchall()==[(0,3,'kind'),(1,2,'owner')]
  after=measured(db);assert after['value']==before['value']
  assert after['vm_steps']*10<before['vm_steps'],(before,after)
  plan=db.execute('EXPLAIN QUERY PLAN SELECT 1 FROM inventory_action_receipts r JOIN character_owners o ON o.uid=r.owner WHERE o.account_id=? AND r.kind=? LIMIT 1',(1,0xd4e)).fetchall()
  assert any(INDEX in str(r)for r in plan),plan
  for kind,expected in cases.items():
   db.execute('INSERT INTO inventory_action_receipts VALUES (?,?,?,?,?,?,?)',('owned-bad','hash',1001,kind,'[]','[]','[]'));db.commit()
   assert outcome(db,1)==expected
   assert outcome(db,2)==before['value']
   db.execute("DELETE FROM inventory_action_receipts WHERE operation_id='owned-bad'");db.commit()
  assert db.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
 report.update(before=before,after=after,plan=plan,old_rows_preserved=len(saved),rejection_cases=cases,repeat_upgrade=True)
 fresh=source.Path(temp)/'fresh.sqlite3';prepare_database(fresh)
 with contextlib.closing(sqlite3.connect(fresh))as db:
  assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='inventory_action_receipts'").fetchone()
 report['fresh_start_keeps_lazy_table']=True

# The stock suite's three session assertions predate the installed 4B9/C55
# notifications. Its other nine storage tests passed in the initial run.
# The normal first receipt writer must create the same index for a fresh save.
case=tests.InventoryActionTests('test_full_count_split_moves_existing_uid_without_sequence_increment');case.setUp()
try:
 tests.split_stack(case.path,1001,tests.split_wire(case.first['slot'],7,10),'owned-first')
 with contextlib.closing(sqlite3.connect(case.path))as db:
  assert db.execute('PRAGMA index_info('+INDEX+')').fetchall()==[(0,3,'kind'),(1,2,'owner')]
 report['first_real_receipt_creates_index']=True
finally:case.doCleanups()
report.update(passed=True,inventory_storage_tests_previously_passed=9,stock_session_assertions_pending_parent_comparison=3,sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in (HERE/'els_server/storage/inventory_actions.py',HERE/'els_server/storage/lifecycle.py',HERE/'verify_index.py',BASE/'els_server/domain/cartridge_registration_rules.py')},natural_battle=False,online_installed=False)
(HERE/'index-results.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
