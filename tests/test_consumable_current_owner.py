from pathlib import Path
from contextlib import closing
import sqlite3,struct,concurrent.futures,tempfile,unittest
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.quick_slots import save_request
from els_server.domain.quick_bindings import item_binding
from els_server.storage.consumables import use

class ConsumableOwnerTests(unittest.TestCase):
    def test_owner_lifecycle_replay_legacy_and_concurrent_economics(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"synthetic.sqlite3"
            root=LocalAccount(LocalState(path),account_id=1);root.enable_characters()
            uid=root.characters.create('ConsumTx',1,'new-consume-tx')['uid'];account=root.for_character(uid);account.get_inventory_snapshot()
            with closing(sqlite3.connect(path)) as db,db:
             db.execute('BEGIN IMMEDIATE');grant_items(db,[dict(template=77000,metadata=2,group=6,quantity=10)],uid)
            wire=struct.pack('>iI',1,6)+b''.join(struct.pack('>ii',k,item_binding(77000) if k==0 else 0) for k in range(6));save_request(path,wire,uid)
            def rows():
             with closing(sqlite3.connect(path)) as db:return {n:db.execute('SELECT * FROM "'+n+'" ORDER BY rowid').fetchall() for n, in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")}
            def reject(f):
             before=rows()
             try:f()
             except ValueError:assert rows()==before
             else:raise AssertionError('Expected rejection')
            checks=[]
            reject(lambda:use(path,uid,bytes(5),'wrong-account',now=2000000000,account_id=2))
            result=use(path,uid,bytes(5),'owned-correct',now=2000000000,account_id=1)
            assert [e.kind for e in result]==[0x114,0x115]
            before=rows();assert [e.kind for e in use(path,uid,bytes(5),'owned-correct',now=2000000001,account_id=1)]==[0x114] and rows()==before
            # Replays check current ownership first, even after committed successful use.
            reject(lambda:use(path,uid,bytes(5),'owned-correct',now=2000000001,account_id=2))
            checks.append('transaction-account-binding-before-initial-use-and-before-replay-original-one115')
            for field in ('requested_at','finalized_at'):
             with closing(sqlite3.connect(path)) as db,db:db.execute('UPDATE character_lifecycle SET '+field+'=1 WHERE uid=?',(uid,))
             reject(lambda:use(path,uid,bytes(5),'owned-correct',now=2000000001,account_id=1))
             reject(lambda:use(path,uid,bytes(5),'unavailable-'+field,now=2000000030,account_id=1))
             with closing(sqlite3.connect(path)) as db,db:db.execute('UPDATE character_lifecycle SET '+field+'=0 WHERE uid=?',(uid,))
            checks.append('pending-and-finalized-owner-refuse-new-and-replay-with-all-tables-exact')
            # Existing local callers can continue omitting optional account_id; lifetime
            # uses a fresh private connection for each call and retains native cooldown.
            assert [e.kind for e in use(path,uid,bytes(5),'legacy-compatible',now=2000000030)]==[0x114,0x115]
            checks.append('optional-owner-argument-compatible-original-local-direct-call')
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
             batches=list(pool.map(lambda _:use(path,uid,bytes(5),'current-concurrent',now=2000000060,account_id=1),range(3)))
            assert sum(e.kind==0x115 for batch in batches for e in batch)==1
            cold=LocalAccount(LocalState(path),account_id=1);cold.enable_characters()
            assert sum(i['count'] for i in cold.for_character(uid).get_inventory_snapshot()['items'] if i['template']==77000)==7
            checks.append('current-owned-concurrent-operation-one-debit-one115-and-cold-count7')

if __name__=='__main__':unittest.main()
