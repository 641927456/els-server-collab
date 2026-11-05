"""The 15-day promotion costume box mirrors its published 7-day sibling."""
import sqlite3,struct,time
from contextlib import closing
from unittest import TestCase
from tests import test_npc_sale as fixture
from els_server.domain.character_rules import CLASSES
from els_server.domain.cubes import catalog as consumer_catalog
from els_server.domain.owned_reward_boxes import BOXES,catalog,outputs_for,plan_for
from els_server.game_data import client_data
from els_server.storage.fixed_cubes import open_cube

SEVEN_DAY=135666
FIFTEEN_DAY=980047
PIECES=(42573,42574,42575,42576,42577,42579)


def rows():
    return {r['template']:r for r in catalog()['boxes']}


def character(cls):
    stage=CLASSES[cls]['stage']
    return dict(unit_type=client_data().unit(cls)['unitType'],unit_class=cls,level=99,
        transcendence=stage>=2,master=False,artifact=None)


def use_payload(uid,option=1):
    return struct.pack('>QBBBI',uid,0,0,0,0)+struct.pack('>i',option)


class PromotionFashionDefinitionTests(TestCase):
    def test_the_fifteen_day_box_is_a_published_owned_reward_box(self):
        self.assertIn(FIFTEEN_DAY,BOXES)
        row=consumer_catalog()[FIFTEEN_DAY]
        self.assertTrue(row['owned_reward_box'])
        # The native item opens on the first click; no choice popup exists.
        self.assertEqual((row['selection_count'],row['entries']),(0,()))
        self.assertEqual(client_data().item(FIFTEEN_DAY)['metadata'],2)

    def test_the_two_siblings_publish_the_same_lineup_for_every_class(self):
        seven=rows()[SEVEN_DAY]['class_outputs']
        fifteen=rows()[FIFTEEN_DAY]['class_outputs']
        self.assertEqual(tuple(seven),tuple(fifteen))
        self.assertEqual(len(fifteen),194)
        # Native lineups differ by class: base classes get five pieces, later
        # classes add the accessory and a second set. Only the days may differ.
        self.assertEqual({len(v) for v in fifteen.values()},{5,6,10,12})
        for cls,outputs in fifteen.items():
            long=outputs_for(FIFTEEN_DAY,character(int(cls)))
            short=outputs_for(SEVEN_DAY,character(int(cls)))
            self.assertEqual([r['template'] for r in long],[r['template'] for r in short])
            self.assertEqual({r['quantity'] for r in long},{1})
            self.assertEqual({r['inventory_days'] for r in long},{15})
            self.assertEqual({r['inventory_days'] for r in short},{7})

    def test_plan_expires_every_piece_fifteen_days_after_the_open(self):
        plan=plan_for(FIFTEEN_DAY,character(152),(),1000)
        self.assertEqual(len(plan),6)
        self.assertEqual({r['expires_at'] for r in plan},{1000+15*86400})
        self.assertEqual({r['quantity'] for r in plan},{1})

    def test_a_class_outside_the_published_lineup_is_refused(self):
        self.assertNotIn('205',rows()[FIFTEEN_DAY]['class_outputs'])
        with self.assertRaises(ValueError):outputs_for(FIFTEEN_DAY,character(205))


class PromotionFashionOpenTests(fixture.SaleTests):
    def setUp(self):
        super().setUp()
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE characters SET unit_type=1,unit_class=152,level=99,transcendence=1,master=0 WHERE uid=1001')

    def open(self,item,operation):
        return open_cube(self.path,1001,FIFTEEN_DAY,use_payload(item['uid']),operation,
            account_id=1,prepare=lambda db:None)

    def pieces(self):
        return [i for i in self.items() if i['template'] in PIECES]

    def expiries(self):
        with closing(sqlite3.connect(self.path)) as db:
            return dict(db.execute('SELECT item_uid,expires_at FROM item_expiration'))

    def test_one_click_consumes_one_box_and_grants_the_six_piece_set(self):
        item=self.grant(FIFTEEN_DAY,2)
        before=time.time()
        events=self.open(item,'promotion-fifteen')
        self.assertEqual([e.kind for e in events],[0xad8,0x197])
        self.assertEqual(next(i['count'] for i in self.items() if i['uid']==item['uid']),1)
        granted=self.pieces()
        self.assertEqual({i['template'] for i in granted},set(PIECES))
        self.assertEqual({i['group'] for i in granted},{27})
        expiries=self.expiries()
        for row in granted:
            self.assertAlmostEqual(expiries[row['uid']]-before,15*86400,delta=120)

    def test_a_replayed_request_does_not_consume_a_second_box(self):
        item=self.grant(FIFTEEN_DAY,2)
        first=self.open(item,'promotion-replay')
        second=self.open(item,'promotion-replay')
        # The retry answers with the stored positions only, so the payload is
        # shorter than the first reply; the box and the pieces stay untouched.
        self.assertEqual([e.kind for e in first],[0xad8,0x197])
        self.assertEqual(second[-1].kind,0x197)
        self.assertEqual(next(i['count'] for i in self.items() if i['uid']==item['uid']),1)
        self.assertEqual(len(self.pieces()),6)

    def test_a_count_of_zero_also_opens_exactly_one_box(self):
        item=self.grant(FIFTEEN_DAY,3)
        events=open_cube(self.path,1001,FIFTEEN_DAY,use_payload(item['uid'],0),'promotion-count-zero',
            account_id=1,prepare=lambda db:None)
        self.assertEqual([e.kind for e in events],[0xad8,0x197])
        self.assertEqual(next(i['count'] for i in self.items() if i['uid']==item['uid']),2)
        self.assertEqual(len(self.pieces()),6)
