"""Native bank browsing is current, read-only and restricted to account siblings."""
import sqlite3
import struct
import unittest
from contextlib import closing
from unittest.mock import patch
from tests import test_npc_sale as fixture
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.protocol.protocol_codec import Event
from tests.test_bank_state import payload as move_payload
from els_server.storage.bank_state import transfer,snapshot,set_capacity
from els_server.storage.bank_view import contents
from els_server.protocol.bank_view_messages import request,acknowledgement
from els_server.protocol.local_messages import wstring


def decode_header(wire):
    result,uid,size=struct.unpack_from('>iQI',wire)
    name=wire[16:16+size].decode('utf-16le')
    tier,count=struct.unpack_from('>iI',wire,16+size)
    return result,uid,name,tier,count,24+size


class BankViewTests(unittest.TestCase):
    setUp=fixture.SaleTests.setUp
    grant=fixture.SaleTests.grant
    dump=fixture.SaleTests.dump
    items=fixture.SaleTests.items

    def deposit(self,slot=7):
        transfer(self.path,1001,move_payload((1,self.gear['slot']),(8,slot),self.gear),'deposit')

    def test_view_uses_group14_without_modifying_owned_bank_or_save(self):
        self.deposit();before=self.dump()
        events=contents(self.path,self.other,wstring('LocalElsword'))
        self.assertEqual(self.dump(),before);self.assertEqual([e.kind for e in events],[0x72f])
        wire=events[0].payload;header=decode_header(wire)
        self.assertEqual(header[:5],(0,1001,'LocalElsword',8,1))
        self.assertEqual(struct.unpack_from('>QQBh',wire,header[-1]),(self.gear['uid'],self.gear['uid'],14,7))
        self.assertEqual(snapshot(self.path,self.other)['bank_items'],[])
        self.assertEqual(snapshot(self.path,1001)['bank_items'][0]['position'],(8,7))

    def test_actual_name_and_all_native_tiers_are_read_from_current_snapshot(self):
        self.deposit()
        for tier in (8,16,24,32,40,48):
            if tier>8:
                with closing(sqlite3.connect(self.path)) as db,db:
                    db.execute('BEGIN IMMEDIATE');set_capacity(db,1001,8,tier)
            header=decode_header(contents(self.path,self.other,wstring('localelsword'))[0].payload)
            self.assertEqual(header[:5],(0,1001,'LocalElsword',tier,1))

    def test_refresh_is_current_and_relogin_does_not_grant_viewed_items(self):
        self.deposit();self.assertEqual(decode_header(contents(self.path,self.other,wstring('LocalElsword'))[0].payload)[4],1)
        transfer(self.path,1001,move_payload((8,7),(1,self.gear['slot']),self.gear),'withdraw')
        before=self.dump()
        again=LocalAccount(LocalState(self.path));again.enable_characters()
        self.assertEqual(decode_header(contents(self.path,self.other,wstring('LocalElsword'))[0].payload)[4],0)
        self.assertEqual(again.for_character(self.other).character()['bank_items'],[])
        self.assertEqual(self.dump(),before)

    def test_unrelated_account_unknown_and_current_names_cannot_be_browsed(self):
        self.deposit()
        for owner,name in ((1001,'LocalElsword'),(self.other,'MissingRole'),(999999,'LocalElsword')):
            before=self.dump()
            with self.assertRaises(ValueError):contents(self.path,owner,wstring(name))
            self.assertEqual(self.dump(),before)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE character_owners SET account_id=2 WHERE uid=?',(self.other,))
        before=self.dump()
        with self.assertRaises(ValueError):contents(self.path,self.other,wstring('LocalElsword'))
        with self.assertRaises(ValueError):contents(self.path,1001,wstring('SaleOther'))
        self.assertEqual(self.dump(),before)

    def test_expired_instances_are_omitted_and_attachments_are_preserved(self):
        from els_server.storage.item_expiration import assign
        from els_server.storage.item_locks import assign as lock
        from els_server.storage.equipment_enhancement import replace
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE');assign(db,1001,self.gear['uid'],2200000000)
            replace(db,1001,self.gear['uid'],0,3);lock(db,1001,self.gear['uid'],2100000000)
        self.deposit();before=self.dump()
        wire=contents(self.path,self.other,wstring('LocalElsword'))[0].payload
        item=snapshot(self.path,1001)['bank_items'][0]['item']
        from els_server.domain.inventory_items import item_body
        self.assertIn(item_body(item),wire)
        with patch('els_server.domain.item_expiration.time.time',return_value=2300000000):
            self.assertEqual(decode_header(contents(self.path,self.other,wstring('LocalElsword'))[0].payload)[4],0)
        self.assertEqual(self.dump(),before)

    def test_bad_names_and_malformed_payloads_fail_without_writes(self):
        malformed=[b'',b'\0'*3,b'\xff'*4,struct.pack('>I',3)+b'abc',wstring('A'),wstring('A'*13),
                   wstring('Two Names'),wstring('LocalElsword')+b'\0',wstring('LocalElsword')[:-1],
                   struct.pack('>I',4)+b'\0\xd8A\0',wstring('e\u0301x'),wstring('XX\0')]
        before=self.dump()
        for wire in malformed:
            with self.subTest(wire=wire),self.assertRaises(ValueError):request(wire)
            with self.assertRaises(ValueError):contents(self.path,self.other,wire)
        self.assertEqual(self.dump(),before)
        for name in ('SaleOther','角色甲','\U00010400X'):
            self.assertEqual(request(wstring(name)),name)

    def test_browse_cannot_turn_group14_into_a_transfer_sort_or_owned_item(self):
        self.deposit();contents(self.path,self.other,wstring('LocalElsword'));before=self.dump()
        from els_server.storage.bank_state import sort
        from els_server.storage.inventory_actions import discard
        for source,destination,context in (((14,7),(1,0),1001),((8,7),(1,0),1001),((14,7),(16,0),0)):
            with self.assertRaises(ValueError):
                transfer(self.path,self.other,move_payload(source,destination,self.gear,context=context),'forged')
        with self.assertRaises(ValueError):sort(self.path,self.other,struct.pack('>i',14),'sort-view')
        # Discard ownership is resolved from the active character, never the view cache.
        wire=struct.pack('>Qi',self.gear['uid'],1)
        with self.assertRaises(ValueError):discard(self.path,self.other,wire,'discard-view')
        self.assertEqual(self.dump(),before)

    def test_session_native_route_failure_reply_and_other_routes(self):
        self.deposit()
        s=LocalSession(self.account.for_character(self.other),enter_town=True,client_build='dx11_260923',enter_dungeon=True,
            npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True)
        s.role='game';s.phase='town_ready';event=Event(0x202,kind=0x72e,payload=wstring('LocalElsword'))
        before=self.dump();answer=s.handle(event,11)
        self.assertEqual([(e.event_id,e.kind) for e in answer],[(0x201,0x72f)])
        self.assertEqual(decode_header(answer[0].payload)[:2],(0,1001))
        self.assertEqual(s.handle(event,11),answer)
        for phase in ('new','game_connected','dungeon_active'):
            s.phase=phase;failed=s.handle(event,12)
            self.assertEqual([e.kind for e in failed],[0x72f]);self.assertEqual(decode_header(failed[0].payload)[:2],(-1,0))
        s.phase='town_ready';s.role='login'
        self.assertEqual(decode_header(s.handle(event,13)[0].payload)[0],-1)
        s.role='game'
        self.assertEqual(decode_header(s.handle(Event(0x202,kind=0x72e,payload=b''),14)[0].payload)[0],-1)
        self.assertEqual(self.dump(),before)
        self.assertEqual([e.kind for e in s.handle(Event(0x202,kind=0x26a,payload=b''),15)],[0x105,0x26b])

    def test_encoding_failure_does_not_create_storage_or_mutate_balance(self):
        before=self.dump()
        with patch('els_server.storage.bank_view.acknowledgement',side_effect=ValueError('wire')):
            with self.assertRaises(ValueError):contents(self.path,self.other,wstring('LocalElsword'))
        self.assertEqual(self.dump(),before)


if __name__=='__main__':unittest.main()
