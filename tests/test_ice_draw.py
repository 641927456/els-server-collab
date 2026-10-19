"""Draw conservation, immutable outcomes, exhaustion and transactional rollback."""
import json,sqlite3,struct,sys,tempfile
from pathlib import Path
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import ice_state
from ice_messages import preview_request,use_request
from inventory_state import InventoryState,grant_items,load_items
from reward_state import RewardState

def request(uid):return struct.pack('>QBBBIi',uid,0,0,0,0,0)
def snapshot(path):
    with closing(sqlite3.connect(path)) as db:return list(db.iterdump())
def seed(path,n):
    RewardState(path);InventoryState(path)
    with closing(sqlite3.connect(path)) as db,db:
        return grant_items(db,[dict(template=800000,metadata=2,group=4,quantity=n)])[0]['uid']
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'ice.sqlite3';uid=seed(path,3)
    payload=request(uid);calls=[]
    def choose(n):calls.append(n);return 0
    first=ice_state.draw(path,payload,'first',randbelow=choose)
    assert struct.unpack_from('>i',first)[0]==0 and calls==[10000]
    before=snapshot(path)
    assert ice_state.draw(path,payload,'first',randbelow=lambda _:1/0)==first
    assert snapshot(path)==before
    try:ice_state.draw(path,request(uid+1),'first')
    except ValueError:pass
    else:raise AssertionError('Conflicting replay accepted')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:ice_state.draw(path,payload,'concurrent',randbelow=lambda n:n-1),range(2)))
    assert results[0]==results[1]
    with closing(sqlite3.connect(path)) as db:
        assert next(i for i in load_items(db) if i['uid']==uid)['count']==1
        assert db.execute('SELECT COUNT(*) FROM ice_draw_receipts').fetchone()[0]==2
        assert db.execute('SELECT revision FROM reward_balances').fetchone()[0]==2
    last=ice_state.draw(path,payload,'last',randbelow=lambda n:5)
    assert ice_state.draw(path,payload,'last')==last
    assert not any(i['uid']==uid for i in InventoryState(path).snapshot()['items'])
    assert len(InventoryState(path).snapshot()['items'])==3
    before=snapshot(path)
    for bad in [payload[:-1],payload+b'\0',request(uid+123),payload]:
        try:ice_state.draw(path,bad,'invalid')
        except ValueError:pass
        else:raise AssertionError('Missing/malformed consumable accepted')
    assert snapshot(path)==before
    uid=seed(path,2);payload=request(uid)
    before=snapshot(path);original=ice_state.result_ack
    def failed_encode(*a,**kw):raise ValueError('simulated codec failure')
    ice_state.result_ack=failed_encode
    try:
        try:ice_state.draw(path,payload,'codec-failure',randbelow=choose)
        except ValueError:pass
        else:raise AssertionError('Encoding failure not propagated')
    finally:ice_state.result_ack=original
    assert snapshot(path)==before
    with closing(sqlite3.connect(path)) as db,db:
        occupied=sum(i['group']==27 for i in load_items(db))
        grant_items(db,[dict(template=81020,metadata=0,group=27,quantity=36-occupied)])
    before=snapshot(path)
    try:ice_state.draw(path,payload,'full',randbelow=choose)
    except ValueError:pass
    else:raise AssertionError('Full bag did not roll back')
    assert snapshot(path)==before
    with closing(sqlite3.connect(path)) as db:
        outcomes=[json.loads(r[0]) for r in db.execute('SELECT outcome_json FROM ice_draw_receipts ORDER BY rowid')]
        assert [o['roll'] for o in outcomes]==[0,9999,5]
        assert all(o['balances']['ed']==0 and o['balances']['experience']==0 for o in outcomes)
    assert preview_request(struct.pack('>iIiBB',800000,1,0,0,0)).keys==(0,)
    assert use_request(request(uid)).uid==uid
print('PASS: one consume/reward per operation, concurrent replay, immutable rolls, exhausted stack removal, persistence, malformed requests, full bag and encode-failure rollback.')
