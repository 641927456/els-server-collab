"""Current manufacture state guards; actual recipe with owned disposable data."""
import sys,sqlite3,struct,tempfile,unittest,json,time
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
sys.dont_write_bytecode=True
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage import manufacture as tx
from els_server.domain import manufacture_flow as flow
from els_server.storage.profession_state import replace,snapshot
from els_server.protocol.profession_messages import ProfessionState
from els_server.storage.character_lifecycle import change,DAY,created,initialize
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.protocol.protocol_codec import Event
NOW=int(time.time())

class Guards(unittest.TestCase):
 def setUp(self):
    self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
    self.path=Path(self.tmp.name)/'own.sqlite3';self.account=LocalAccount(LocalState(self.path));self.account.enable_characters()
    with closing(sqlite3.connect(self.path)) as db,db:
        db.execute('UPDATE characters SET level=99 WHERE uid=1001')
        db.execute('UPDATE reward_balances SET ed=400000 WHERE uid=1001')
        plans=[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=q) for t,q in [(118205,9),(701000,15)]]
        grant_items(db,plans)
        replace(db,1001,1,0,ProfessionState(3,3,0,{},0,400))
    self.payload=struct.pack('>iiqI',10078927,1,-1,0)
 def dump(self):
    with closing(sqlite3.connect(self.path)) as db:return tuple(db.iterdump())
 def schedule(self):
    from els_server.storage.character_selection import save
    save(self.path,1,[],[1001])
    change(self.path,1,1001,'schedule')
 def perform(self,op='current'):
    return tx.execute(self.path,1001,1,self.payload,op,now=NOW)
 def session(self):
    from els_server.config import ServerConfig
    s=LocalSession(self.account,**ServerConfig().session_options());s.role='game';s.phase='town_ready'
    return s
 def test_active_current_recipe_keeps_original_transaction_and_replay(self):
    result=self.perform();self.assertEqual(result['audit']['rewards'],{78927:3});before=self.dump()
    replay=self.perform();self.assertTrue(replay['replayed']);self.assertEqual(before,self.dump())
 def test_pending_delete_cannot_spend_material_ED_or_craft(self):
    self.schedule();before=self.dump()
    with self.assertRaises(ValueError):self.perform()
    self.assertEqual(self.dump(),before)
 def test_pending_committed_receipt_refuses_and_restore_reuses_original(self):
    self.perform();self.schedule();before=self.dump()
    with self.assertRaises(ValueError):self.perform()
    self.assertEqual(self.dump(),before)
    with patch('els_server.storage.character_lifecycle.current_time',return_value=NOW+DAY+1):change(self.path,1,1001,'restore')
    before=self.dump();self.assertTrue(self.perform()['replayed']);self.assertEqual(self.dump(),before)
 def test_finalized_role_cannot_craft_or_replay(self):
    self.perform();self.schedule()
    with patch('els_server.storage.character_lifecycle.current_time',return_value=NOW+3*DAY+1):change(self.path,1,1001,'finalize')
    before=self.dump()
    for op in ['current','another']:
        with self.subTest(op=op),self.assertRaises(ValueError):self.perform(op)
    self.assertEqual(self.dump(),before)
 def test_pending_role_cannot_choose_profession(self):
    with closing(sqlite3.connect(self.path)) as db,db:
        db.execute('BEGIN IMMEDIATE');current=snapshot(db,1001,1);replace(db,1001,1,current['revision'],ProfessionState())
    self.schedule();before=self.dump()
    with self.assertRaises(ValueError):tx.select_alchemist(self.path,1001,1,bytes([3]))
    self.assertEqual(self.dump(),before)
 def test_stale_selected_store_identity_rejected_before_storage(self):
    s=self.session();s.account.store=SimpleNamespace(uid=1002,path=self.path)
    with patch.object(tx,'execute',return_value={'response':b'notcalled','leveled':False,'requires_inventory_sync':False}) as run:
        events=flow.handle(s,Event(0x202,performers=(0,),kind=0x198,payload=self.payload),17)
    self.assertEqual(run.call_count,0);self.assertEqual(struct.unpack_from('>i',events[0].payload)[0],-1)
 def test_obsolete_playing_lease_refuses_both_mutating_routes(self):
    s=self.session();root=s.account.root
    s.identity={'id':1};s.released=False;s.application=SimpleNamespace(playing={1:object()},accounts={1:root})
    for kind,payload in [(0x198,self.payload),(0x4c2,bytes([3]))]:
        with self.subTest(kind=kind),patch.object(tx,'execute',return_value={'response':b'notcalled','leveled':False,'requires_inventory_sync':False}) as craft,patch.object(tx,'select_alchemist',return_value=b'notcalled') as choose:
            events=flow.handle(s,Event(0x202,performers=(0,),kind=kind,payload=payload),17)
            self.assertEqual(craft.call_count,0);self.assertEqual(choose.call_count,0)
            self.assertEqual(struct.unpack_from('>i',events[0].payload)[0],-1)
 def test_wrong_account_still_rejected_in_transaction(self):
    before=self.dump()
    with self.assertRaises(ValueError):tx.execute(self.path,1001,2,self.payload,'foreign',now=NOW)
    self.assertEqual(self.dump(),before)
if __name__=='__main__':unittest.main(verbosity=2)
