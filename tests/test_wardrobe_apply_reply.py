"""A wardrobe apply reply must not announce unrelated registered appearances."""
from contextlib import closing
from pathlib import Path
import sqlite3
import struct
import tempfile
import unittest

from els_server.domain.local_session import LocalAccount
from els_server.domain.wardrobe import catalog, definition
from els_server.domain.inventory_items import FASHION_EQUIP_SLOTS, TEMPLATE_BAG_GROUPS
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import load_items
from els_server.storage.wardrobe import change, counts
from els_server.protocol.wardrobe_messages import initialization


def reply_map(event):
    result, size = struct.unpack_from('>iI', event.payload)
    assert result == 0
    return dict(struct.unpack_from('>ii', event.payload, 8 + n*8) for n in range(size))


class WardrobeApplyReplyTests(unittest.TestCase):
    def setUp(self):
        # Keep test saves beside the checkout, including when run on Windows.
        self.tmp = tempfile.TemporaryDirectory(prefix='own-wardrobe-', dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'game.sqlite3'
        self.account = LocalAccount(LocalState(self.path))
        self.account.enable_characters()
        self.owner, self.account_id = self.account.uid, self.account.account_id
        selected = {}
        for template in sorted(FASHION_EQUIP_SLOTS):
            if template not in catalog():
                continue
            d = definition(template)
            raw, position = d['record'], d['equip_position']
            if raw[0xd2] in (0, 1) and raw[0xd3] in (0, 1) and not raw[8] & 4 and position in (8, 9):
                selected.setdefault(position, [])
                if len(selected[position]) < 2:
                    selected[position].append(template)
            if len(selected) == 2 and all(len(v) == 2 for v in selected.values()):
                break
        self.assertEqual({p:len(v) for p,v in selected.items()}, {8:2, 9:2})
        self.rows = []
        with closing(sqlite3.connect(self.path)) as db, db:
            for n, (position, templates) in enumerate(sorted(selected.items())):
                source, base = templates
                for uid, template, slot in ((880001+n, source, 30+n*2), (880011+n, base, 31+n*2)):
                    db.execute('INSERT INTO inventory_items VALUES(?,?,?,?,?,?,?)', (uid,self.owner,template,0,1,TEMPLATE_BAG_GROUPS[template],slot))
                self.rows.append((position, source, 880011+n))
        for uid in (880001, 880002, 880011, 880012):
            ack = change(self.path,self.owner,self.account_id,0x4af,struct.pack('>Q',uid),f'register-{uid}')
            self.assertTrue(reply_map(ack))

    def apply(self, rows, operation):
        body = struct.pack('>I',len(rows))+b''.join(struct.pack('>iiQIiii',p,t,u,3,0,0,0) for p,t,u in rows)
        return change(self.path,self.owner,self.account_id,0x4b1,body,operation)

    def state(self):
        with closing(sqlite3.connect(self.path)) as db:
            return load_items(db,self.owner), counts(db,self.owner,self.account_id), list(db.iterdump())

    def test_apply_and_replay_keep_registry_but_announce_no_registration(self):
        before, registry, _ = self.state()
        ack = self.apply(self.rows,'apply-two')
        self.assertEqual(reply_map(ack),{})
        self.assertEqual(struct.unpack_from('>I',ack.payload,8)[0],2)
        after, registered, saved = self.state()
        self.assertEqual(registered,registry)
        items = {i['uid']:i for i in after}
        for _,template,uid in self.rows:
            self.assertEqual(items[uid]['appearance_template'],template)
        strip = lambda xs:[{k:v for k,v in i.items() if k!='appearance_template'} for i in xs]
        self.assertEqual(strip(before),strip(after))
        self.assertEqual(self.apply(self.rows,'apply-two').payload,ack.payload)
        self.assertEqual(self.state()[2],saved)
        cold = LocalAccount(LocalState(self.path));cold.enable_characters()
        self.assertEqual(cold.get_inventory_snapshot(),self.account.get_inventory_snapshot())
        initial = initialization(registered)
        self.assertEqual(reply_map(initial),registry)

    def test_late_batch_refusal_preserves_items_registry_and_receipts(self):
        before = self.state()
        position, template, uid = self.rows[-1]
        with self.assertRaises(ValueError):
            self.apply(self.rows[:-1]+[(position+100,template,uid)],'refused')
        self.assertEqual(self.state(),before)


if __name__ == '__main__':
    unittest.main()
