"""Source-only710022 manual use; no EP offer, client process, or retail producer."""
import sqlite3,struct,tempfile,unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.quick_slots import save_request,encode,empty
from els_server.storage.consumables import use
from els_server.domain.consumables import ordinary,require_usable,manual_magic_potion_definition
from els_server.domain.inventory_items import TEMPLATE_MAX_STACKS,TEMPLATE_BAG_GROUPS,VERIFIED_TEMPLATES
from els_server.domain.quick_bindings import item_binding

class ManualMagicPotionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'game.sqlite3'
        root=LocalAccount(LocalState(self.path));root.enable_characters()
        self.uid=root.characters.create('MagicOwner',1,'manual-owner')['uid']
        self.other=root.characters.create('MagicOther',5,'manual-other')['uid']
        self.account=root.for_character(self.uid)
        self.account.get_inventory_snapshot();root.for_character(self.other).get_inventory_snapshot()

    def grant(self,n):
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            items=grant_items(db,[dict(template=710022,metadata=2,group=6,quantity=n)],self.uid)
        save_request(self.path,struct.pack('>i',1)+encode({**empty(),0:item_binding(710022)}),self.uid)
        return items

    def items(self):
        with closing(sqlite3.connect(self.path)) as db:return load_items(db,self.uid)

    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as db:return tuple(db.iterdump())

    def consume(self,op,now=2000000000):
        return use(self.path,self.uid,bytes(5),op,now=now,account_id=1)

    def reject(self,fn,error=ValueError):
        before=self.snapshot()
        with self.assertRaises(error):fn()
        self.assertEqual(self.snapshot(),before)

    def test_owned_manual_current_UID_receipt_cold_and_guards(self):
        self.assertEqual(manual_magic_potion_definition(),dict(template=710022,metadata=2,group=6,max_stack=500))
        self.assertEqual((VERIFIED_TEMPLATES[710022],TEMPLATE_BAG_GROUPS[710022],TEMPLATE_MAX_STACKS[710022]),(2,6,999))
        self.assertEqual((TEMPLATE_MAX_STACKS[723604],TEMPLATE_MAX_STACKS[723609]),(1,1000))
        meta=ordinary(710022);self.assertEqual((meta['cooldown_group'],meta['cooldown_seconds']),(19,30))
        self.assertEqual(meta['effects'],[struct.pack('<6I',19,0,100,0,0,0).hex()])
        first=self.grant(999)[0];second=self.grant(2)[0]
        wallet=self.account.get_reward_balances()
        answer=self.consume('first')
        self.assertEqual([e.kind for e in answer],[0x114,0x115])
        self.assertEqual(answer[1].payload,struct.pack('>Qi?Q?',self.uid,710022,False,0,False))
        self.assertEqual(next(i for i in self.items() if i['uid']==first['uid'])['count'],998)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT cooldown_group,ready_at FROM consumable_cooldowns WHERE owner=?',(self.uid,)).fetchall(),[(19,2000000030)])
            self.assertEqual(db.execute('SELECT item_uid,template FROM consumable_uses').fetchall(),[(first['uid'],710022)])
        self.reject(lambda:self.consume('cooling',2000000029))
        for op in ('foreign','first'):
            self.reject(lambda:use(self.path,self.uid,bytes(5),op,now=2000000040,account_id=2))
        with self.assertRaises(ValueError):require_usable(710022,99,automatic=True)
        self.reject(lambda:use(self.path,self.uid,bytes(5),'automatic',now=2000000040,account_id=1,automatic_use=True))
        for column in ('requested_at','finalized_at'):
            with closing(sqlite3.connect(self.path)) as db,db:
                self.assertEqual(db.execute(f'UPDATE character_lifecycle SET {column}=2000000001 WHERE uid=?',(self.uid,)).rowcount,1)
            self.reject(lambda:self.consume('first',2000000040))
            self.reject(lambda:self.consume('new-'+column,2000000040))
            with closing(sqlite3.connect(self.path)) as db,db:
                db.execute('UPDATE character_lifecycle SET requested_at=0,finalized_at=0 WHERE uid=?',(self.uid,))
        # Private fixture relocation/deletion probes historical receipt identity.
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE inventory_items SET slot=20 WHERE uid=?',(first['uid'],))
            db.execute('UPDATE inventory_items SET slot=? WHERE uid=?',(first['slot'],second['uid']))
            db.execute('DELETE FROM inventory_items WHERE uid=?',(first['uid'],))
        before=self.snapshot();self.assertEqual([e.kind for e in self.consume('first',2000000040)],[0x114]);self.assertEqual(self.snapshot(),before)
        self.assertEqual([e.kind for e in self.consume('current',2000000040)],[0x114,0x115])
        self.assertEqual(next(i for i in self.items() if i['uid']==second['uid'])['count'],1)
        cold=LocalAccount(LocalState(self.path,self.uid));cold.enable_characters()
        self.assertEqual(cold.get_inventory_snapshot()['items'],self.items())
        self.assertEqual(self.account.get_reward_balances(),wallet)
        with closing(sqlite3.connect(self.path)) as db:self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_encoder_late_SQL_rollback_expiration_and_legacy_last(self):
        item=self.grant(2)[0];self.consume('prior')
        with patch('els_server.storage.consumables.effect',side_effect=ValueError('private710022 encoder fault')):
            self.reject(lambda:self.consume('encoder',2000000030))
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute("CREATE TRIGGER manual_magic_fault BEFORE INSERT ON consumable_uses WHEN NEW.operation_id='sql-fault' BEGIN SELECT RAISE(ABORT,'private710022');END")
        self.reject(lambda:self.consume('sql-fault',2000000030),sqlite3.IntegrityError)
        from els_server.storage.item_expiration import assign
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE');assign(db,self.uid,item['uid'],2000000029)
        self.reject(lambda:self.consume('expired',2000000030))
        # A new unexpired owned instance uses the same existing generic path;
        # the expired instance remains intact and is never a consumption source.
        fresh=self.grant(1)[0]
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('DROP TABLE character_lifecycle')
        self.assertEqual([e.kind for e in self.consume('legacy-last',2000000030)],[0x114,0x115])
        self.assertFalse(any(i['uid']==fresh['uid'] for i in self.items()))
        self.assertEqual(next(i for i in self.items() if i['uid']==item['uid'])['count'],1)
        self.reject(lambda:self.consume('no-valid-source',2000000060))

if __name__=='__main__':unittest.main()
