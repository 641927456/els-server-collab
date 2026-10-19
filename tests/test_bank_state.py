"""Private bank transaction, exact-instance preservation and relog coverage."""
import json,sqlite3,struct
from contextlib import closing
from unittest.mock import patch
from tests import test_npc_sale as fixture
from els_server.storage.bank_state import transfer,sort,snapshot,remove_due
from els_server.storage.inventory_state import load_items
from els_server.protocol.bank_messages import transfer_request,restore_map
from els_server.protocol.local_messages import player_initialization


def payload(source,destination,item,quantity=None,context=0):
    return struct.pack('>BiBiiQi',*source,*destination,item['count'] if quantity is None else quantity,context,item['template'])


class BankTests(fixture.SaleTests):
    def bank(self):return snapshot(self.path,1001)['bank_items']

    def deposit(self,item,slot=0,quantity=None,operation='deposit'):
        return transfer(self.path,1001,payload((item['group'],item['slot']),(8,slot),item,quantity),operation)

    def test_deposit_withdraw_full_gear_preserves_uid_and_attachments_on_relogin(self):
        from els_server.storage.equipment_enhancement import replace
        from els_server.storage.item_expiration import assign
        from els_server.storage.item_locks import assign as lock
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE');replace(db,1001,self.gear['uid'],0,3)
            assign(db,1001,self.gear['uid'],2200000000);lock(db,1001,self.gear['uid'],2100000000)
        item=next(i for i in self.items() if i['uid']==self.gear['uid'])
        self.deposit(item)
        self.assertNotIn(item['uid'],{i['uid'] for i in self.items()});self.assertEqual(self.bank()[0]['item'],item)
        with closing(sqlite3.connect(self.path)) as db:self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
        data=fixture.LocalAccount(fixture.LocalState(self.path));data.enable_characters()
        self.assertEqual(data.character()['bank_items'][0]['item'],item)
        transfer(self.path,1001,payload((8,0),(1,item['slot']),item),'withdraw')
        self.assertEqual(next(i for i in self.items() if i['uid']==item['uid']),item);self.assertEqual(self.bank(),[])

    def test_partial_deposit_withdraw_merge_and_counts_are_conserved(self):
        item=self.grant(701000,20);self.deposit(item,quantity=7)
        bank=self.bank()[0]['item'];self.assertNotEqual(bank['uid'],item['uid'])
        self.assertEqual(bank['count'],7)
        transfer(self.path,1001,payload((8,0),(3,item['slot']),bank,3),'withdraw')
        self.assertEqual(self.bank()[0]['item']['count'],4)
        self.assertEqual(next(i['count'] for i in self.items() if i['uid']==item['uid']),16)
        transfer(self.path,1001,payload((8,0),(3,item['slot']),self.bank()[0]['item']),'withdraw-rest')
        self.assertEqual(self.bank(),[]);self.assertEqual(next(i['count'] for i in self.items() if i['uid']==item['uid']),20)

    def test_swap_different_items_and_wrong_tab_rollback(self):
        second=self.grant(30160);self.deposit(self.gear)
        transfer(self.path,1001,payload((second['group'],second['slot']),(8,0),second),'swap')
        self.assertEqual(self.bank()[0]['item']['uid'],second['uid'])
        self.assertEqual(next(i for i in self.items() if i['uid']==self.gear['uid'])['slot'],second['slot'])
        before=self.dump()
        with self.assertRaises(ValueError):transfer(self.path,1001,payload((8,0),(3,1),second),'bad-tab')
        self.assertEqual(self.dump(),before)

    def test_foreign_owner_context_and_unowned_capacity_rejected(self):
        for source,dest,owner,context in (((1,self.gear['slot']),(8,8),1001,0),
                ((1,self.gear['slot']),(8,0),self.other,0),((1,self.gear['slot']),(8,0),1001,self.other),
                ((1,self.gear['slot']),(16,8),1001,0)):
            before=self.dump()
            with self.assertRaises(ValueError):transfer(self.path,owner,payload(source,dest,self.gear,context=context),'bad')
            self.assertEqual(self.dump(),before)

    def test_retry_uses_current_bank_slot_without_second_transfer(self):
        p=payload((1,self.gear['slot']),(8,0),self.gear)
        transfer(self.path,1001,p,'once');second=self.grant(30160)
        transfer(self.path,1001,payload((second['group'],second['slot']),(8,0),second),'swap')
        before=self.dump();wire=transfer(self.path,1001,p,'once')
        self.assertEqual(self.dump(),before)
        # First changed position is now empty, second contains replacement.
        self.assertEqual(struct.unpack_from('>Q',wire,4+324)[0],second['uid'])

    def test_sort_order_and_replay_are_absolute_without_new_item_rows(self):
        second=self.grant(30160);self.deposit(self.gear,5);self.deposit(second,3,operation='second')
        wire=sort(self.path,1001,struct.pack('>i',8),'sort')
        self.assertEqual([e['item']['template'] for e in self.bank()],[30160,60100])
        self.assertEqual([e['position'] for e in self.bank()],[(8,0),(8,1)])
        self.assertEqual(struct.unpack('>iIQQiI',wire),(8,2,second['uid'],self.gear['uid'],0,0))
        before=self.dump();self.assertEqual(sort(self.path,1001,struct.pack('>i',8),'sort'),wire);self.assertEqual(self.dump(),before)

    def test_encoder_failure_rolls_back_both_containers_and_uid_allocation(self):
        before=self.dump()
        with patch('els_server.storage.bank_state.transfer_ack',side_effect=ValueError('wire')):
            with self.assertRaises(ValueError):self.deposit(self.gear)
        self.assertEqual(self.dump(),before)

    def test_bank_expiration_frees_slot_and_cannot_resurrect(self):
        from els_server.storage.item_expiration import assign
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE');assign(db,1001,self.gear['uid'],2200000000)
        item=next(i for i in self.items() if i['uid']==self.gear['uid']);self.deposit(item)
        with patch('els_server.domain.item_expiration.time.time',return_value=2300000000):
            self.assertEqual(self.bank(),[]);events=remove_due(self.path,1001)
            self.assertEqual(events[0].kind,0x105)
            self.assertEqual(remove_due(self.path,1001),[])
            with self.assertRaises(ValueError):transfer(self.path,1001,payload((8,0),(1,item['slot']),item),'expired')
        self.assertEqual(self.bank(),[])

    def test_initialization_includes_bank_record_and_native_membership_capacity(self):
        self.deposit(self.gear)
        character=self.account.character();self.assertEqual(character['bank_capacities'],{8:8,16:8})
        wire=restore_map(self.items(),character['bank_items'])
        self.assertEqual(struct.unpack_from('>I',wire)[0],len(self.items())+1)
        self.assertIn(struct.pack('>QQBh',self.gear['uid'],self.gear['uid'],8,0),wire)
        message=player_initialization(items=self.items(),character=character)
        self.assertIn(wire,message.payload)


for _name in list(vars(fixture.SaleTests)):
    if _name.startswith('test_') and _name not in vars(BankTests):setattr(BankTests,_name,None)
