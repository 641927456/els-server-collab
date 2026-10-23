"""Current formal-source ice draw replay, isolated SQLite only."""
import sys,json,sqlite3,struct,tempfile,hashlib,unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
sys.dont_write_bytecode=True
from els_server.storage.reward_state import RewardState
from els_server.storage.inventory_state import InventoryState,grant_items,load_items
from els_server.storage import ice_state as ice
from els_server.protocol.ice_messages import result_events
from els_server.domain.fashion_state import move_ack

def request(uid):return struct.pack('>QBBBIi',uid,0,0,0,0,0)
def dump(path):
    with closing(sqlite3.connect(path)) as db:return list(db.iterdump())
class IceReplay(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'owned.sqlite3'
        RewardState(self.path);InventoryState(self.path)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE reward_balances SET ed=100 WHERE uid=1001')
            self.source=grant_items(db,[dict(template=800000,metadata=2,group=4,quantity=2)])[0]
        self.payload=request(self.source['uid'])
        self.first=ice.draw(self.path,self.payload,'owned-draw',randbelow=lambda _:0)
        with closing(sqlite3.connect(self.path)) as db:
            self.history=db.execute('SELECT * FROM ice_draw_receipts').fetchone()
            self.items=load_items(db)
            self.reward=next(i for i in self.items if i['uid']!=self.source['uid'])
    def change(self,*,remove=False):
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE inventory_items SET slot=8 WHERE uid=?',(self.source['uid'],))
            if remove:db.execute('DELETE FROM inventory_items WHERE uid=?',(self.reward['uid'],))
            else:db.execute('UPDATE inventory_items SET slot=9 WHERE uid=?',(self.reward['uid'],))
            replacement=grant_items(db,[dict(template=self.reward['template'],metadata=self.reward['metadata'],group=self.reward['group'],quantity=1)])[0]
            db.execute('UPDATE reward_balances SET ed=37,revision=revision+1 WHERE uid=1001')
            rows=load_items(db);current={(i['group'],i['slot']):i for i in rows}
            points={(self.source['group'],self.source['slot']),(self.reward['group'],self.reward['slot']),(self.source['group'],8)}
            if not remove:points.add((self.reward['group'],9))
        return move_ack([(p,current.get(p)) for p in sorted(points)])[:-4],replacement
    def test_unchanged_replay_stays_compatible(self):
        before=dump(self.path)
        self.assertEqual(ice.draw(self.path,self.payload,'owned-draw',randbelow=lambda _:1/0),self.first)
        self.assertEqual(dump(self.path),before)
    def test_moved_UIDs_replacement_and_current_ED(self):
        vector,_=self.change();before=dump(self.path)
        replay=ice.draw(self.path,self.payload,'owned-draw',randbelow=lambda _:1/0)
        self.assertEqual(result_events(replay)[0].payload,vector)
        self.assertEqual(struct.unpack_from('>Q',replay,len(replay)-15)[0],37)
        self.assertEqual(replay[:24],self.first[:24])
        self.assertEqual(dump(self.path),before)
    def test_removed_reward_does_not_resurrect(self):
        vector,_=self.change(remove=True);before=dump(self.path)
        replay=ice.draw(self.path,self.payload,'owned-draw',randbelow=lambda _:1/0)
        self.assertEqual(result_events(replay)[0].payload,vector)
        self.assertEqual(dump(self.path),before)
    def test_corrupt_history_fails_without_side_effect(self):
        with closing(sqlite3.connect(self.path)) as db,db:db.execute("UPDATE ice_draw_receipts SET outcome_json='{}'")
        before=dump(self.path)
        with self.assertRaises(ValueError):ice.draw(self.path,self.payload,'owned-draw',randbelow=lambda _:1/0)
        self.assertEqual(dump(self.path),before)
    def test_exhausted_source_and_later_occupant_are_current(self):
        payload=request(self.source['uid'])
        first=ice.draw(self.path,payload,'exhausted-draw',randbelow=lambda _:0)
        with closing(sqlite3.connect(self.path)) as db,db:
            self.assertFalse(any(i['uid']==self.source['uid'] for i in load_items(db)))
            replacement=grant_items(db,[dict(template=800000,metadata=2,group=4,quantity=3)])[0]
            rows=load_items(db);current={(i['group'],i['slot']):i for i in rows}
            audit=json.loads(db.execute("SELECT outcome_json FROM ice_draw_receipts WHERE operation_id='exhausted-draw'").fetchone()[0])
            points={(i['group'],i['slot']) for i in [audit['consumed'],*audit['reward']]}
            expected=move_ack([(p,current.get(p)) for p in sorted(points)])[:-4]
        before=dump(self.path)
        replay=ice.draw(self.path,payload,'exhausted-draw',randbelow=lambda _:1/0)
        self.assertEqual(result_events(replay)[0].payload,expected)
        self.assertEqual(dump(self.path),before)
    def test_multi_stack_reward_and_repeated_concurrent_replay(self):
        from concurrent.futures import ThreadPoolExecutor
        from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
        pool=ice.role_pools(1)[800000];template=130165
        roll=sum(w for t,w in pool[:next(i for i,(t,w) in enumerate(pool) if t==template)])
        with closing(sqlite3.connect(self.path)) as db,db:
            reward=grant_items(db,[dict(template=template,metadata=VERIFIED_TEMPLATES[template],group=TEMPLATE_BAG_GROUPS[template],quantity=TEMPLATE_MAX_STACKS[template]-1)])[0]
            source=grant_items(db,[dict(template=800000,metadata=2,group=4,quantity=2)])[0]
        payload=request(source['uid']);first=ice.draw(self.path,payload,'split-draw',randbelow=lambda _:roll)
        with closing(sqlite3.connect(self.path)) as db,db:
            history=json.loads(db.execute("SELECT outcome_json FROM ice_draw_receipts WHERE operation_id='split-draw'").fetchone()[0])
            self.assertEqual(len(history['reward']),2)
            oldpos={(i['group'],i['slot']) for i in [history['consumed'],*history['reward']]}
            for n,item in enumerate(history['reward']):db.execute('UPDATE inventory_items SET slot=? WHERE uid=?',(20+n,item['uid']))
            rows=load_items(db);points=oldpos|{(i['group'],i['slot']) for i in rows if i['uid'] in {r['uid'] for r in history['reward']}}
            current={(i['group'],i['slot']):i for i in rows}
            expected=move_ack([(p,current.get(p)) for p in sorted(points)])[:-4]
        before=dump(self.path)
        with ThreadPoolExecutor(max_workers=2) as workers:
            results=list(workers.map(lambda _:ice.draw(self.path,payload,'split-draw',randbelow=lambda _:1/0),range(2)))
        self.assertEqual(results[0],results[1])
        self.assertEqual(result_events(results[0])[0].payload,expected)
        self.assertEqual(dump(self.path),before)
    def test_retry_payload_conflict(self):
        before=dump(self.path)
        with self.assertRaises(ValueError):ice.draw(self.path,request(self.source['uid']+1),'owned-draw')
        self.assertEqual(dump(self.path),before)
    def test_replay_encoder_failure_preserves_original_receipt(self):
        self.change();before=dump(self.path)
        with patch('els_server.domain.fashion_state.move_ack',side_effect=ValueError('injected replay codec failure')):
            with self.assertRaises(ValueError):ice.draw(self.path,self.payload,'owned-draw',randbelow=lambda _:1/0)
        self.assertEqual(dump(self.path),before)
if __name__=='__main__':unittest.main()
