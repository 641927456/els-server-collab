"""Paid ordinary enhancement: real costs, no free upgrades or retry redraws."""
import sqlite3,struct,unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from tests import test_npc_sale as fixture
from els_server.storage.paid_enhancement import enhance
from els_server.storage.equipment_enhancement import replace
from els_server.domain.paid_enhancement import quote,fee,outcome,RATES
from els_server.protocol.paid_enhancement_messages import request
from els_server.domain.local_session import LocalSession
from els_server.protocol.protocol_codec import Event


def payload(uid,**changes):
    d=dict(uid=uid,mode=0,profession=0,a=0,b=0,c=1,d=0,context=0,e=0);d.update(changes)
    return struct.pack('>QiiBBBBiB',*d.values())


class PaidEnhancementTests(unittest.TestCase):
    setUp=fixture.SaleTests.setUp
    grant=fixture.SaleTests.grant
    items=fixture.SaleTests.items
    dump=fixture.SaleTests.dump
    money=fixture.SaleTests.money

    def fund(self,ed=100000000):
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE reward_balances SET ed=? WHERE uid=1001',(ed,))

    def gear_now(self):return next(i for i in self.items() if i['uid']==self.gear['uid'])

    def test_success_deducts_fee_and_one_stone_and_survives_relogin(self):
        self.fund();stone=self.grant(163135,3);before=self.money();cost=fee(60100,0)
        answer=enhance(self.path,1001,payload(self.gear['uid']),'once',lambda n:0)
        self.assertEqual([e.kind for e in answer],[0x600]);self.assertEqual(self.money(),before-cost)
        self.assertEqual(self.gear_now()['enhancement'],1)
        self.assertEqual(next(i['count'] for i in self.items() if i['uid']==stone['uid']),2)
        self.assertEqual(struct.unpack_from('>iQiQi',answer[0].payload),(0,before-cost,1,self.gear['uid'],1))

    def test_cobo_stone_priority_and_empty_slot_removal(self):
        self.fund();regular=self.grant(163135,2);cobo=self.grant(163284)
        enhance(self.path,1001,payload(self.gear['uid']),'once',lambda n:0)
        self.assertNotIn(cobo['uid'],{i['uid'] for i in self.items()})
        self.assertEqual(next(i['count'] for i in self.items() if i['uid']==regular['uid']),2)

    def test_rate_boundaries_and_level7_down_and_reset(self):
        for level,rates in enumerate(RATES):
            self.assertEqual(sum(rates),10000);offset=0
            for code,weight,new in zip((1,3,4,5),rates,(level+1,level,level-1,0)):
                if weight:
                    for roll in (offset,offset+weight-1):self.assertEqual(outcome(level,roll),(code,new))
                offset+=weight
        for roll,code,updated in ((500,3,7),(2000,4,6),(5000,5,0)):
            self.fund();self.grant(163135)
            current=self.gear_now().get('enhancement',0)
            with closing(sqlite3.connect(self.path)) as db,db:db.execute('BEGIN IMMEDIATE');replace(db,1001,self.gear['uid'],current,7)
            before=self.money();cost=fee(60100,7)
            wire=enhance(self.path,1001,payload(self.gear['uid']),str(roll),lambda n:roll)[0].payload
            self.assertEqual(struct.unpack_from('>iQiQi',wire),(0,before-cost,code,self.gear['uid'],updated))
            self.assertEqual(self.gear_now().get('enhancement',0),updated)

    def test_retry_returns_current_absolute_state_without_redraw_or_old_upgrade(self):
        self.fund();self.grant(163135,3);p=payload(self.gear['uid'])
        enhance(self.path,1001,p,'once',lambda n:0);enhance(self.path,1001,p,'twice',lambda n:0)
        before=self.dump()
        wire=enhance(self.path,1001,p,'once',lambda n:self.fail('Retry redrew'))[0].payload
        self.assertEqual(self.dump(),before)
        self.assertEqual(struct.unpack_from('>iQiQi',wire),(0,self.money(),0,self.gear['uid'],2))
        with self.assertRaisesRegex(ValueError,'Conflicting'):enhance(self.path,1001,payload(self.gear['uid'],context=1),'once')

    def test_no_stone_money_other_owner_locked_expired_and_high_level_reject(self):
        self.fund();p=payload(self.gear['uid']);before=self.dump()
        with self.assertRaises(ValueError):enhance(self.path,1001,p,'no-stone')
        self.assertEqual(self.dump(),before);self.grant(163135);self.fund(0);before=self.dump()
        with self.assertRaises(ValueError):enhance(self.path,1001,p,'no-money')
        self.assertEqual(self.dump(),before);self.fund();before=self.dump()
        with self.assertRaises(ValueError):enhance(self.path,self.other,p,'foreign')
        self.assertEqual(self.dump(),before)
        for changed in (dict(lock_until=2200000000),dict(expires_at=1000000000),dict(enhancement=8)):
            with self.assertRaises(ValueError):quote(dict(self.gear_now(),**changed))

    def test_bad_packets_modes_and_random_sources_fail_without_mutation(self):
        self.fund();self.grant(163135,2);before=self.dump()
        for wire in (b'',payload(self.gear['uid'])[:-1],payload(self.gear['uid'])+b'\0',
                payload(0),payload(self.gear['uid'],mode=1),payload(self.gear['uid'],profession=1),
                payload(self.gear['uid'],a=1),payload(self.gear['uid'],b=1),payload(self.gear['uid'],c=0),
                payload(self.gear['uid'],d=1),payload(self.gear['uid'],e=1)):
            with self.assertRaises(ValueError):request(wire)
        for invalid in (-1,10000,True):
            with self.assertRaises(ValueError):enhance(self.path,1001,payload(self.gear['uid']),str(invalid),lambda n:invalid)
        self.assertEqual(self.dump(),before)

    def test_encoder_failure_rolls_back_material_money_equipment_and_receipt(self):
        self.fund();self.grant(163135);before=self.dump()
        with patch('els_server.storage.paid_enhancement.acknowledgement',side_effect=ValueError('wire')):
            with self.assertRaises(ValueError):enhance(self.path,1001,payload(self.gear['uid']),'fail',lambda n:0)
        self.assertEqual(self.dump(),before)

    def test_concurrent_duplicate_consumes_once(self):
        self.fund();self.grant(163135,3);before=self.money();cost=fee(60100,0);p=payload(self.gear['uid'])
        with ThreadPoolExecutor(max_workers=2) as pool:
            result=list(pool.map(lambda _:enhance(self.path,1001,p,'same',lambda n:0),range(2)))
        self.assertEqual(self.money(),before-cost);self.assertEqual(self.gear_now()['enhancement'],1)
        self.assertEqual(sorted(struct.unpack_from('>i',r[0].payload,12)[0] for r in result),[0,1])

    def test_session_handler_and_wrong_phase_complete_native_wait(self):
        self.fund();self.grant(163135)
        s=LocalSession(self.account,enter_town=True,enter_dungeon=True,client_build='dx11_260923',
            npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True)
        s.role='game';s.phase='town_ready';e=Event(0x202,kind=0x5ff,payload=payload(self.gear['uid']))
        answer=s.handle(e,1);self.assertEqual([a.kind for a in answer],[0x600]);self.assertEqual(self.gear_now()['enhancement'],1)
        before=self.dump();s.phase='dungeon_active'
        self.assertEqual(struct.unpack_from('>i',s.handle(e,2)[0].payload)[0],-1)
        self.assertEqual(self.dump(),before)


if __name__=='__main__':unittest.main()
