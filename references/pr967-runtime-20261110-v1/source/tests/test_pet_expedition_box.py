"""Expedition box: one debit, one drawn grant, one replayable receipt."""
import json,struct,sqlite3,tempfile,unittest
from contextlib import closing
from pathlib import Path

from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage import pet_expedition_box as store
from els_server.domain.pet_expedition_box import BOXES,definitions


def prepare(db):
    pass


def rewards_of(event):
    """The displayed reward map of a0x197 result: i32 code,field,exp,I count."""
    count=struct.unpack_from('>I',event.payload,12)[0]
    return [struct.unpack_from('>ii',event.payload,16+8*index)for index in range(count)]


class ExpeditionBox(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='expedition-box-');self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'game.sqlite3'
        self.account=LocalAccount(LocalState(self.path),account_id=1)
        self.account.enable_characters()
        self.account.get_inventory_snapshot()

    def grant(self,template,quantity=1):
        from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
        with closing(sqlite3.connect(self.path))as db,db:
            return grant_items(db,[dict(template=template,metadata=VERIFIED_TEMPLATES[template],
                group=TEMPLATE_BAG_GROUPS[template],quantity=quantity)],1001)[0]

    def payload(self,uid):
        return struct.pack('>QBBBI',uid,0,0,0,0)+struct.pack('>i',0)

    def open(self,uid,operation,pick):
        return store.open_box(self.path,1001,1,self.payload(uid),operation,prepare=prepare,
            randbelow=lambda n:pick)

    def counts(self):
        with closing(sqlite3.connect(self.path))as db:
            return dict(db.execute('SELECT template,count FROM inventory_items WHERE owner=1001 AND template IN (135984,135985,135977,135974)').fetchall())

    def dump(self):
        with closing(sqlite3.connect(self.path))as db:
            return tuple(db.iterdump())

    def test_pool_is_the_approved_local_pair(self):
        rows=definitions()
        self.assertEqual(sorted(rows),list(BOXES))
        for row in rows.values():
            self.assertEqual(row['group'],21)
            self.assertEqual(row['selection_count'],0)
            self.assertEqual(sum(e['weight']for e in row['entries']),10000)

    def test_opens_only_one_box_and_grants_the_drawn_entry(self):
        box=self.grant(135984,2)
        self.assertEqual(self.counts(),{135984:2})
        events=self.open(box['uid'],'exp-box-a',0)
        self.assertEqual([e.kind for e in events][-1],0x197)
        # pick0 falls in the135977 8000-weight slice.
        self.assertEqual(self.counts(),{135984:1,135977:1})
        with closing(sqlite3.connect(self.path))as db:
            self.assertEqual(db.execute('SELECT count FROM inventory_items WHERE owner=1001 AND template=135984').fetchone(),(1,))

    def test_evolution_box_draws_the_upper_slice(self):
        box=self.grant(135985,1)
        self.open(box['uid'],'exp-box-b',5000)
        self.assertEqual(self.counts(),{135974:1})

    def test_replay_does_not_roll_the_pool_again(self):
        box=self.grant(135984,1)
        first=self.open(box['uid'],'exp-box-c',0)
        after=self.dump()
        replay=self.open(box['uid'],'exp-box-c',8000)
        self.assertEqual(after,self.dump())
        # The first reply carries the0xAD8 move vector; a replay reprojects the
        # same positions through the shared0x105 update, as the choice box does.
        # The granted list itself must be identical: the pool is never re-rolled.
        self.assertEqual(first[-1].kind,0x197)
        self.assertEqual(replay[-1].kind,0x197)
        self.assertEqual(rewards_of(replay[-1]),rewards_of(first[-1]))
        self.assertEqual(rewards_of(first[-1]),[(135977,1)])
        self.assertEqual(self.counts(),{135977:1})

    def test_conflicting_replay_is_refused(self):
        box=self.grant(135984,1)
        self.open(box['uid'],'exp-box-d',0)
        before=self.dump()
        with self.assertRaises(ValueError):
            self.open(box['uid'],'exp-box-other',0)
        self.assertEqual(before,self.dump())

    def test_foreign_template_is_outside_the_pool(self):
        other=self.grant(135977,1)
        before=self.dump()
        with self.assertRaises(ValueError):
            self.open(other['uid'],'exp-box-e',0)
        self.assertEqual(before,self.dump())


if __name__=='__main__':
    unittest.main()
