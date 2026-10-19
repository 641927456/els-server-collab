import json,sqlite3,struct,tempfile,unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from els_server.domain.item_expiration import date_string,expired,MINIMUM,MAXIMUM
from els_server.domain.inventory_items import item_body
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.item_expiration import assign,remove_due,forget


class ExpirationTests(unittest.TestCase):
    def test_wire_matches_native_and_attribute_offsets(self):
        from datetime import datetime
        from els_server.domain.item_expiration import CLIENT_ZONE
        proof=json.loads(Path('analysis/integration-20261015/timed-item-wire-native.json').read_text(encoding='utf8'))['proof']
        self.assertEqual(len(proof['rows']),16)
        for row in proof['rows']:
            if row['template']==711611 and not row['date']:continue # Permanent pass is deliberately not issued.
            item=dict(uid=1001,template=row['template'],metadata=row['metadata'],group=row['group'],slot=0,count=1)
            if row['date']:item['expires_at']=int(datetime.strptime(row['date'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=CLIENT_ZONE).timestamp())
            self.assertEqual(item_body(item).hex(),row['wire_hex'])
        base=dict(uid=1,template=100,metadata=1,group=1,slot=0,count=1,expires_at=1792049000)
        plain=item_body(base);attrs=item_body(dict(base,attributes=[1,0,0,0],durability=1234))
        self.assertEqual(len(attrs),len(plain)+16)
        self.assertEqual(attrs[176:],plain[160:])
        self.assertEqual(struct.unpack_from('>h',attrs,9),(1234,))
        self.assertFalse(expired(base,now=base['expires_at']))
        self.assertTrue(expired(base,now=base['expires_at']+1))
        for value in (True,1.0,MINIMUM-1,MAXIMUM+1):
            with self.assertRaises(ValueError):date_string(value)

    def fixture(self,directory):
        path=Path(directory)/'save.db';account=LocalAccount(LocalState(path));account.enable_characters();account.enable_inventory()
        return path,account

    def test_grant_reopen_stacks_and_expiration_atomicity(self):
        with tempfile.TemporaryDirectory() as directory:
            path,account=self.fixture(directory);deadline=1792049000
            plan=dict(template=77000,metadata=2,group=6,quantity=2)
            with closing(sqlite3.connect(path)) as db,db:
                db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
                normal=grant_items(db,[plan])[0]
                timed=grant_items(db,[dict(plan,expires_at=deadline)])[0]
                later=grant_items(db,[dict(plan,expires_at=deadline+60)])[0]
                merged=grant_items(db,[dict(plan,expires_at=deadline)])[0]
                self.assertEqual(merged['uid'],timed['uid']);self.assertEqual(merged['count'],4)
            reloaded=LocalAccount(LocalState(path));reloaded.enable_characters();reloaded.enable_inventory()
            saved=reloaded.get_inventory_snapshot()['items'];self.assertEqual(len(saved),3)
            self.assertEqual(remove_due(path,1001,now=deadline),[])
            with patch('els_server.protocol.expiration_messages.notice',side_effect=RuntimeError('codec')):
                with self.assertRaises(RuntimeError):remove_due(path,1001,now=deadline+1)
            self.assertEqual(reloaded.get_inventory_snapshot()['items'],saved)
            self.assertEqual(remove_due(path,1002,now=deadline+1),[])
            reply=remove_due(path,1001,now=deadline+1)[0]
            self.assertEqual(reply.kind,0x1c6)
            self.assertEqual(struct.unpack('>IQiI',reply.payload),(1,timed['uid'],77000,0))
            self.assertEqual(remove_due(path,1001,now=deadline+1),[])
            self.assertEqual({i['uid'] for i in reloaded.get_inventory_snapshot()['items']},{normal['uid'],later['uid']})
            with closing(sqlite3.connect(path)) as db,db:
                db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
                forget(db,later['uid']);db.execute('DELETE FROM inventory_items WHERE uid=?',(later['uid'],))
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
                self.assertEqual(db.execute('SELECT count(*) FROM expired_item_receipts').fetchone()[0],1)

    def test_move_preserves_uid_deadline_and_periodic_notices(self):
        from els_server.domain.fashion_state import move_fashion
        with tempfile.TemporaryDirectory() as directory:
            path,account=self.fixture(directory);deadline=1792049000
            with closing(sqlite3.connect(path)) as db,db:
                db.execute('BEGIN IMMEDIATE');item=grant_items(db,[dict(template=81021,metadata=0,group=27,quantity=1,expires_at=deadline)])[0]
            with patch('time.time',return_value=deadline):
                move_fashion(path,struct.pack('>BiBiB',27,item['slot'],27,1,0))
            self.assertEqual(account.get_inventory_snapshot()['items'][0]['expires_at'],deadline)
            before=account.get_inventory_snapshot()
            with patch('time.time',return_value=deadline+1):
                with self.assertRaises(ValueError):move_fashion(path,struct.pack('>BiBiB',27,1,27,0,0))
            self.assertEqual(account.get_inventory_snapshot(),before)
            s=LocalSession(account,client_build='dx11_260923',enter_town=True,enter_dungeon=True,npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True)
            s.role='game';s.phase='town_ready'
            with patch('time.time',return_value=deadline+1):
                self.assertEqual([e.kind for e in s.periodic_notifications()],[0x1c6])
                self.assertEqual(s.periodic_notifications(),[])
            self.assertEqual(account.get_inventory_snapshot()['items'],[])

    def test_transaction_checks_expiry_without_sweep_and_consumption_cleans_deadline(self):
        from els_server.storage.consumables import use
        from els_server.storage.quick_slots import save_request,encode,empty
        with tempfile.TemporaryDirectory() as directory:
            path,account=self.fixture(directory);deadline=1792049000
            with closing(sqlite3.connect(path)) as db,db:
                db.execute('BEGIN IMMEDIATE')
                old=grant_items(db,[dict(template=77000,metadata=2,group=6,quantity=1,expires_at=deadline-10)])[0]
                current=grant_items(db,[dict(template=77000,metadata=2,group=6,quantity=1,expires_at=deadline)])[0]
            save_request(path,struct.pack('>i',1)+encode({**empty(),5:1}))
            use(path,1001,struct.pack('>HBBB',5,0,0,0),'last-second',now=deadline)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT item_uid FROM item_expiration').fetchall(),[(old['uid'],)])
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
                self.assertEqual(db.execute('SELECT item_uid FROM consumable_uses').fetchall(),[(current['uid'],)])
            before=account.get_inventory_snapshot()
            with self.assertRaises(ValueError):use(path,1001,struct.pack('>HBBB',5,0,0,0),'expired',now=deadline+40)
            self.assertEqual(account.get_inventory_snapshot(),before)

    def test_offline_expired_equipment_cleans_dependent_rows_without_duplicate_receipts(self):
        from els_server.storage.equipment_attributes import replace_attributes
        from els_server.storage.equipment_durability import replace_durability
        with tempfile.TemporaryDirectory() as directory:
            path,account=self.fixture(directory);deadline=1792049000
            with closing(sqlite3.connect(path)) as db,db:
                db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
                item=grant_items(db,[dict(template=60100,metadata=1,group=1,quantity=1,expires_at=deadline)])[0]
                replace_attributes(db,1001,item['uid'],[0,0,0,0],[1,0,0,0])
                replace_durability(db,1001,item['uid'],10000,9000)
            self.assertEqual(len(remove_due(path,1001,now=deadline+100)),1)
            self.assertEqual(remove_due(path,1001,now=deadline+101),[])
            with closing(sqlite3.connect(path)) as db:
                for table in ('item_expiration','equipment_attributes','equipment_durability'):
                    self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
                self.assertEqual(db.execute('SELECT count(*) FROM expired_item_receipts').fetchone()[0],1)


if __name__=='__main__':unittest.main()
