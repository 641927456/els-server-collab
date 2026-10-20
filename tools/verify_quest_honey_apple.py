"""79065 inventory-to-native-use admission; all data is private QA state."""
from contextlib import closing
import concurrent.futures
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import sys
import traceback
from unittest.mock import patch

O=Path(__file__).resolve().parents[1]
P=O
sys.path.insert(0,str(P))
from els_server.domain.consumables import require_usable
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.quick_slots import save_request
from els_server.domain.quick_bindings import item_binding
from els_server.storage.consumables import use
import tempfile,atexit
private=tempfile.TemporaryDirectory(prefix='els-honey-apple-qa-')
atexit.register(private.cleanup)
F=Path(private.name);path=F/'game.sqlite3'

a=LocalAccount(LocalState(path));a.enable_characters()
uid=a.characters.create('HoneyLithia',15,'honey-qa')['uid']
other=a.characters.create('HoneyElse',1,'honey-other')['uid']
for owner in (uid,other):a.for_character(owner).get_inventory_snapshot()

def snapshot():
    with closing(sqlite3.connect(path)) as db:
        return {n:db.execute('SELECT * FROM "'+n+'" ORDER BY rowid').fetchall()
                for n, in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}

def total():
    with closing(sqlite3.connect(path)) as db:
        return sum(i['count'] for i in load_items(db,uid) if i['template']==79065)

def reject(fn):
    before=snapshot()
    try:fn()
    except (ValueError,sqlite3.IntegrityError):assert snapshot()==before
    else:raise AssertionError('Expected rejection')

checks=[]
try:
    q=json.loads((P/'els_server/data/story_quests.json').read_text(encoding='utf8'))['quests']['28380']
    assert q['QuestCondition']['m_eUnitType']=={'1':15}
    assert q['Reward']['m_bEnable']==1 and not q['m_bIsTimeEvent']
    assert q['Reward']['m_vecItem']=={'1':{'m_iPeriod':0,'m_iQuantity':30,'m_iItemID':79065,'m_sSocketOption':0}}
    try:require_usable(79065,1,automatic=True)
    except ValueError:pass
    else:raise AssertionError('Unqualified79065 pet automation admitted')
    meta=require_usable(79065,1)
    assert (meta['cooldown_group'],meta['cooldown_seconds'])==(10,30)
    assert meta['effects']==[struct.pack('<6I',k,0,50,0,0,0).hex() for k in (19,13)]
    assert bytes.fromhex(meta['record_hex'])[209]==0
    assert struct.unpack_from('<I',bytes.fromhex(meta['record_hex']),168)[0]==0
    checks.append('pinned-current-source-level0-cooldown10-30-and-ordered-MP50-HP50')
    with closing(sqlite3.connect(path)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        grant_items(db,[dict(template=79065,metadata=2,group=6,quantity=30)],uid)
    binding=struct.pack('>iI',1,6)+b''.join(struct.pack('>ii',k,item_binding(79065) if k==0 else 0) for k in range(6))
    assert save_request(path,binding,uid).payload[:4]==bytes(4)
    answer=use(path,uid,bytes(5),'honey-first',now=2000000000)
    assert [e.kind for e in answer]==[0x114,0x115]
    assert answer[1].payload==struct.pack('>Qi?Q?',uid,79065,False,0,False)
    assert total()==29
    before=snapshot();retry=use(path,uid,bytes(5),'honey-first',now=2000000001)
    assert [e.kind for e in retry]==[0x114] and snapshot()==before
    reject(lambda:use(path,uid,bytes(5),'honey-cooling',now=2000000029))
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('SELECT cooldown_group,ready_at FROM consumable_cooldowns WHERE owner=?',(uid,)).fetchall()==[(10,2000000030)]
    cold=LocalAccount(LocalState(path,uid));cold.enable_characters()
    assert sum(i['count'] for i in cold.get_inventory_snapshot()['items'] if i['template']==79065)==29
    checks.append('native-115-once-debit1-idempotent-retry-cooldown-and-cold-reopen')
    reject(lambda:use(path,other,bytes(5),'foreign-honey',now=2000000030))
    reject(lambda:use(path,uid,b'\xff\x00\x00\x00\x00','bad-slot',now=2000000030))
    with patch('els_server.storage.consumables.effect',side_effect=ValueError('honey-encode-fault')):
        reject(lambda:use(path,uid,bytes(5),'honey-encode-fault',now=2000000030))
    with closing(sqlite3.connect(path)) as db,db:
        db.execute("CREATE TRIGGER honey_fault BEFORE INSERT ON consumable_uses WHEN NEW.operation_id='honey-sql-fault' BEGIN SELECT RAISE(ABORT,'honey-fault'); END")
    reject(lambda:use(path,uid,bytes(5),'honey-sql-fault',now=2000000030))
    checks.append('foreign-owner-invalid-slot-encoder-and-SQL-abort-no-changes')
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        out=list(pool.map(lambda _:use(path,uid,bytes(5),'honey-concurrent',now=2000000030),range(4)))
    assert total()==28 and sum(e.kind==0x115 for batch in out for e in batch)==1
    checks.append('same-operation-concurrency-one-debit-and-one-native-effect')
    with closing(sqlite3.connect(path)) as db,db:
        db.execute('UPDATE inventory_items SET count=1 WHERE owner=? AND template=?',(uid,79065))
    last=use(path,uid,bytes(5),'honey-last',now=2000000060)
    assert total()==0 and [e.kind for e in last]==[0x114,0x115]
    before=snapshot();retry=use(path,uid,bytes(5),'honey-last',now=2000000061)
    assert [e.kind for e in retry]==[0x114] and snapshot()==before
    reject(lambda:use(path,uid,bytes(5),'honey-empty',now=2000000090))
    checks.append('last-unit-delete-retry-and-empty-rejection')
    r=dict(ok=True,checks=checks,private_API_created_level1_role=True,
           inventory_supplied_from_exact_source_quantity_as_QA=True,
           actual_quest_claim_or_natural_gameplay=False,native_GUI_or_battle=False,
           client_formula_or_timer_changes=0,SDK=False,formal_DB_access=False)
    print(json.dumps(r))
except BaseException:
    print(json.dumps(dict(completed=checks,error=traceback.format_exc()),indent=2));raise
