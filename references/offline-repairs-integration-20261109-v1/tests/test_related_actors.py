"""Normal and retired actors through adjacent equipment and skill writers."""
from contextlib import closing
import json
import sqlite3
import struct
import sys
import unittest
import bootstrap
from test_item_contracts import OwnedFixture
from els_server.storage import (paid_enhancement,equipment_restoration,equipment_enhancement,
    skill_traits,quick_slots,artifact_progression)
from els_server.domain import skill_traits as trait_rules
from els_server.domain import artifact_progression as artifact_rules
from els_server.domain.owned_scroll_families import catalog as scrolls


class RelatedActors(unittest.TestCase):
    def prepare(self,kind):
        f=OwnedFixture('artifact' if kind=='artifact-wear'else'expansion');self.addCleanup(f.close)
        if kind=='enhance':
            item=f.add(30154);f.add(163284,2)
            payload=struct.pack('>QiiBBBBiB',item['uid'],0,0,0,0,1,0,0,0)
            return f,lambda op:paid_enhancement.enhance(f.path,1001,payload,op,randbelow=lambda n:0,account_id=1)
        if kind=='restore':
            item=f.add(30154)
            with closing(sqlite3.connect(f.path))as db,db:
                db.execute('BEGIN');equipment_enhancement.replace(db,1001,item['uid'],0,-8)
            template=next(iter(scrolls()['restoration']));f.add(template)
            payload=struct.pack('>QiB',item['uid'],template,0)
            return f,lambda op:equipment_restoration.restore(f.path,1001,payload,op,account_id=1)
        if kind=='quick-slots':
            payload=struct.pack('>i',1)+quick_slots.encode(quick_slots.empty())
            return f,lambda op:quick_slots.save_request(f.path,payload,1001)
        if kind in ('trait-choose','trait-reset'):
            character=f.account.character();bases=set(trait_rules.bases(character))
            skill,notes=next((skill,notes)for (unit_class,skill),notes in trait_rules.catalog().items()if unit_class==1 and skill in bases)
            note=next(iter(notes));payload=struct.pack('>ii',skill,note)
            if kind=='trait-choose':return f,lambda op:skill_traits.choose(f.path,1001,1,payload,op)
            skill_traits.choose(f.path,1001,1,payload,'owned-choose')
            payload=struct.pack('>iiQB',skill,note,0,1)
            return f,lambda op:skill_traits.reset(f.path,1001,1,payload,op,prepare=lambda db:None)
        if kind=='artifact-wear':
            template=next(iter(artifact_rules.catalog()['equipment']));item=f.add(template)
            target=artifact_rules.slots(template)[0]
            payload=struct.pack('>BiBiB',1,item['slot'],24,target,0)
            return f,lambda op:artifact_progression.move(f.path,payload,1001,account_id=1,
                session_id='00000000-0000-4000-8000-000000000003',sequence=1)
        raise AssertionError(kind)

    def test_normal_adjacent_actions_still_work(self):
        for kind in ('enhance','restore','quick-slots','trait-choose','trait-reset','artifact-wear'):
            with self.subTest(kind=kind):
                f,action=self.prepare(kind);self.assertIsNotNone(action('owned-normal-'+kind))

    def test_pending_and_finalized_actors_cannot_mutate_adjacent_state(self):
        for kind in ('enhance','restore','quick-slots','trait-choose','trait-reset','artifact-wear'):
            for finalized in (False,True):
                with self.subTest(kind=kind,finalized=finalized):
                    f,action=self.prepare(kind);f.lifecycle(finalized);before=f.dump()
                    with self.assertRaisesRegex(ValueError,'pending deletion or finalized'):action('owned-retired-'+kind)
                    self.assertEqual(f.dump(),before)

    def test_old_requests_remain_rejected_after_actor_retirement(self):
        for kind in ('enhance','restore','quick-slots','trait-choose','trait-reset','artifact-wear'):
            with self.subTest(kind=kind):
                f,action=self.prepare(kind);action('owned-replay');f.lifecycle();before=f.dump()
                with self.assertRaisesRegex(ValueError,'pending deletion or finalized'):action('owned-replay')
                self.assertEqual(f.dump(),before)
