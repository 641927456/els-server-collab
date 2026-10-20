"""New710000 positive economy compositions using the actual storage path."""
from contextlib import closing
from functools import partial
import concurrent.futures
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import traceback
from unittest.mock import patch

O = Path(__file__).resolve().parents[1]
P = O
sys.path.insert(0,str(P))
from els_server.domain.consumables import ordinary
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items, load_items
from els_server.storage.quick_slots import save_request
from els_server.storage.consumables import use
from els_server.domain.quick_bindings import item_binding

import atexit
private = tempfile.TemporaryDirectory(prefix='els-recovery-qa-')
atexit.register(private.cleanup)
F = Path(private.name)
path = F/'game.sqlite3'
account = LocalAccount(LocalState(path))
account.enable_characters()
a = account.characters.create('RecoveryOne', 1, 'recovery-one')['uid']
b = account.characters.create('RecoveryTwo', 15, 'recovery-two')['uid']
for uid in (a, b):
    account.for_character(uid).get_inventory_snapshot()

def items(uid=a):
    with closing(sqlite3.connect(path)) as db:
        return load_items(db, uid)

def count(uid=a):
    return sum(i['count'] for i in items(uid) if i['template']==710000)

def snapshot():
    with closing(sqlite3.connect(path)) as db:
        return {n:db.execute('SELECT * FROM "'+n+'" ORDER BY rowid').fetchall()
                for n, in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}

def reject(fn):
    before = snapshot()
    try:fn()
    except (ValueError, sqlite3.IntegrityError):assert snapshot()==before
    else:raise AssertionError('Expected refusal')

def seed(uid,n):
    with closing(sqlite3.connect(path)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        return grant_items(db,[dict(template=710000,metadata=2,group=6,quantity=n)],uid)[0]

def bind(uid):
    return save_request(path,struct.pack('>iI',1,6)+b''.join(
        struct.pack('>ii',k,item_binding(710000) if k==0 else 0) for k in range(6)),uid)

checks=[]
try:
    # The input already belongs to the current admitted quest catalog. Do not
    # confuse similarly numbered Artifact socket options with item sources.
    source=json.loads((P/'els_server/data/story_quests.json').read_text())
    for q,n in (('7780',5),('7790',10)):
        assert any(r['m_iItemID']==710000 and r['m_iQuantity']==n
                   for r in source['quests'][q]['Reward']['m_vecItem'].values())
    meta=ordinary(710000)
    assert (meta['cooldown_group'],meta['cooldown_seconds'])==(15,30)
    assert [struct.unpack('<6I',bytes.fromhex(v)) for v in meta['effects']]==[
        (13,0,100,0,0,0),(19,0,100,0,0,0)]
    checks.append('exact-existing-quest-producer-and-native-effect-vector')
    seed(a,5);bind(a);other=items(b)
    answer=use(path,a,bytes(5),'recovery-first',now=2000000000)
    assert [e.kind for e in answer]==[0x114,0x115]
    assert answer[1].payload==struct.pack('>Qi?Q?',a,710000,False,0,False)
    assert count()==4 and items(b)==other
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('SELECT cooldown_group,ready_at FROM consumable_cooldowns WHERE owner=?',(a,)).fetchall()==[(15,2000000030)]
    cold=LocalAccount(LocalState(path,a));cold.enable_characters()
    assert sum(i['count'] for i in cold.get_inventory_snapshot()['items'] if i['template']==710000)==4
    checks.append('one-success-one-native-input-debit-and-cold-read')
    before=snapshot();retry=use(path,a,bytes(5),'recovery-first',now=2000000001)
    assert [e.kind for e in retry]==[0x114] and snapshot()==before
    reject(lambda:use(path,a,bytes(5),'recovery-cooling',now=2000000029))
    reject(lambda:use(path,b,bytes(5),'foreign-no-binding',now=2000000001))
    checks.append('retries-cooling-and-other-role-do-not-debit-or-repeat-effect')
    with patch('els_server.storage.consumables.effect',side_effect=ValueError('recovery-encoder-fault')):
        reject(lambda:use(path,a,bytes(5),'recovery-fault',now=2000000030))
    with closing(sqlite3.connect(path)) as db,db:
        db.execute("CREATE TRIGGER recovery_receipt_fault BEFORE INSERT ON consumable_uses WHEN NEW.operation_id='recovery-sql-fault' BEGIN SELECT RAISE(ABORT,'recovery-fault'); END")
    reject(lambda:use(path,a,bytes(5),'recovery-sql-fault',now=2000000030))
    checks.append('count-cooldown-and-receipt-rollback-together')
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        answers=list(pool.map(lambda _:use(path,a,bytes(5),'recovery-concurrent',now=2000000030),range(4)))
    assert count()==3 and sum(e.kind==0x115 for out in answers for e in out)==1
    checks.append('same-operation-concurrency-one-debit-one-effect')
    seed(b,1);bind(b);use(path,b,bytes(5),'recovery-last',now=2000000030)
    assert count(b)==0
    checks.append('last-unit-removed-without-cross-role-effect')
    result=dict(ok=True,checks=checks,private_API_created_saves=True,
                real_native_game=False,new_client_math_or_timers=False,new_templates=0,
                new_reward_producers=0,SDK=False)
    print(json.dumps(result))
except BaseException:
    print(json.dumps(dict(completed=checks,error=traceback.format_exc()),indent=2))
    raise
