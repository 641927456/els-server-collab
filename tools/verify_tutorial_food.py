"""Current tutorial reward products: private inventory to native use inputs."""
from contextlib import closing
import concurrent.futures
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
private=tempfile.TemporaryDirectory(prefix='els-tutorial-food-qa-')
atexit.register(private.cleanup)
F=Path(private.name);path=F/'game.sqlite3'
a=LocalAccount(LocalState(path));a.enable_characters()
uid=a.characters.create('FoodLithia',15,'food-qa')['uid']
other=a.characters.create('FoodElse',1,'food-other')['uid']
for owner in (uid,other):a.for_character(owner).get_inventory_snapshot()

def snapshot():
    with closing(sqlite3.connect(path)) as db:
        return {n:db.execute('SELECT * FROM "'+n+'" ORDER BY rowid').fetchall()
                for n, in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}

def total(t,owner=uid):
    with closing(sqlite3.connect(path)) as db:
        return sum(i['count'] for i in load_items(db,owner) if i['template']==t)

def reject(fn):
    before=snapshot()
    try:fn()
    except (ValueError,sqlite3.IntegrityError):assert snapshot()==before
    else:raise AssertionError('Expected rejection')

checks=[]
try:
    q=json.loads((P/'els_server/data/story_quests.json').read_text())['quests']['28060']
    assert q['QuestCondition']['m_eUnitType']=={'1':15}
    outputs=q['Reward']['m_vecItem']
    assert {(r['m_iItemID'],r['m_iQuantity']) for r in outputs.values()}=={(79063,20),(79064,20)}
    with closing(sqlite3.connect(path)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        grant_items(db,[dict(template=t,metadata=2,group=6,quantity=20) for t in (79063,79064)],uid)
    binding=struct.pack('>iI',1,6)+b''.join(struct.pack('>ii',k,item_binding(79063 if k==0 else 79064) if k<2 else 0) for k in range(6))
    assert save_request(path,binding,uid).payload[:4]==bytes(4)
    checks.append('exact-current-Lithia-reward-template-quantity-and-owned-bindings')
    for t,slot,group,effect in ((79063,0,2,13),(79064,1,5,19)):
        meta=require_usable(t,1)
        assert (meta['cooldown_group'],meta['cooldown_seconds'])==(group,30)
        assert meta['effects']==[struct.pack('<6I',effect,0,50,0,0,0).hex()]
        payload=struct.pack('>HBBB',slot,0,0,0)
        answer=use(path,uid,payload,'food-first-'+str(t),now=2000000000)
        assert [e.kind for e in answer]==[0x114,0x115]
        assert answer[1].payload==struct.pack('>Qi?Q?',uid,t,False,0,False)
        assert total(t)==19
        before=snapshot();retry=use(path,uid,payload,'food-first-'+str(t),now=2000000001)
        assert [e.kind for e in retry]==[0x114] and snapshot()==before
        reject(lambda:use(path,uid,payload,'food-cooling-'+str(t),now=2000000029))
        checks.append('native-level1-use-once-retry-cooling-'+str(t))
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('SELECT cooldown_group,ready_at FROM consumable_cooldowns WHERE owner=? ORDER BY cooldown_group',(uid,)).fetchall()==[(2,2000000030),(5,2000000030)]
    checks.append('bread-and-juice-use-same-time-independent-native-cooldowns')
    cold=LocalAccount(LocalState(path,uid));cold.enable_characters()
    assert {t:sum(i['count'] for i in cold.get_inventory_snapshot()['items'] if i['template']==t) for t in (79063,79064)}=={79063:19,79064:19}
    checks.append('counts-and-both-cooldowns-persist-after-cold-reopen')
    reject(lambda:use(path,other,bytes(5),'foreign-food',now=2000000030))
    with patch('els_server.storage.consumables.effect',side_effect=ValueError('food-encode-fault')):
        reject(lambda:use(path,uid,bytes(5),'food-encode-fault',now=2000000030))
    with closing(sqlite3.connect(path)) as db,db:
        db.execute("CREATE TRIGGER food_fault BEFORE INSERT ON consumable_uses WHEN NEW.operation_id='food-sql-fault' BEGIN SELECT RAISE(ABORT,'food-fault'); END")
    reject(lambda:use(path,uid,bytes(5),'food-sql-fault',now=2000000030))
    checks.append('foreign-owner-encoder-and-SQL-abort-without-economic-changes')
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        out=list(pool.map(lambda _:use(path,uid,bytes(5),'food-concurrent',now=2000000030),range(4)))
    assert total(79063)==18 and sum(e.kind==0x115 for batch in out for e in batch)==1
    checks.append('same-operation-concurrency-single-count-and-native-effect')
    r=dict(ok=True,checks=checks,private_API_created_level1_role=True,
           source_quantities_are_QA_inventory_inputs=True,actual_quest_claim_not_repeated=True,
           native_GUI_or_battle=False,client_formula_or_timer_changes=0,SDK=False)
    print(json.dumps(r))
except BaseException:
    print(json.dumps(dict(completed=checks,error=traceback.format_exc()),indent=2));raise
