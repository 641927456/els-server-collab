"""Sealing retries describe current UID positions and replacement occupants."""
import json,sqlite3,unittest
from els_server.storage.equipment_receipt_state import current_changes

class SealPositions(unittest.TestCase):
    def test_moved_target_and_stamp_preserve_current_state(self):
        for kind in(0x270,0x272):
            with self.subTest(kind=kind),sqlite3.connect(':memory:')as db:
                db.execute('CREATE TABLE inventory_action_receipts(operation_id TEXT,owner INT,kind INT,before_json TEXT,after_json TEXT)')
                history=[dict(uid=3001,group=1,slot=0,sealed=False),dict(uid=3002,group=4,slot=0,count=3)]
                db.execute('INSERT INTO inventory_action_receipts VALUES (?,?,?,?,?)',('op',1001,kind,json.dumps(history),json.dumps(history)))
                target=dict(uid=3001,group=1,slot=7,sealed=False)
                stamp=dict(uid=3002,group=4,slot=8,count=1)
                replacements=[dict(uid=4001,group=1,slot=0),dict(uid=4002,group=4,slot=0)]
                self.assertEqual(current_changes(db,'op',1001,kind,[(1,0),(4,0)],[*replacements,target,stamp]),
                                 [((1,0),replacements[0]),((4,0),replacements[1]),((1,7),target),((4,8),stamp)])
                self.assertEqual(current_changes(db,'op',1001,kind,[(1,0),(4,0)],replacements),
                                 [((1,0),replacements[0]),((4,0),replacements[1])])
                with self.assertRaises(ValueError):current_changes(db,'op',1002,kind,[(1,0)],replacements)

if __name__=='__main__':unittest.main()
