"""Actual original-board SQL producer/delivery, including unsold return negative."""
from pathlib import Path
import os,sys
BASE=Path(os.environ['ELS_FULL_SOURCE']).resolve()
ORIGINAL=Path(os.environ['ELS_ORIGINAL_SOURCE']).resolve()
sys.dont_write_bytecode=True;sys.path[:0]=[str(BASE),str(BASE/'vendor')]
from types import SimpleNamespace
env=SimpleNamespace(BASE=ORIGINAL,W=Path(__file__).resolve().parent)
from contextlib import closing
from types import SimpleNamespace
import importlib.util,json,sqlite3,struct,unittest
import board_test_fixture as fixtures
from els_server.storage import trade_board_state as fixed
from els_server.storage.enhancement_progress import replace as progress
from els_server.domain.trade_board_authority import TradeBoardAuthority

spec=importlib.util.spec_from_file_location('original_board_state',env.BASE/'els_server/storage/trade_board_state.py')
original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)

class BoardProgressTests(unittest.TestCase):
    setUp=fixtures.ExchangeTests.setUp
    tearDown=fixtures.ExchangeTests.tearDown
    items=fixtures.ExchangeTests.items
    dump=fixtures.ExchangeTests.dump
    def authority(self,owner,account,kind):
        a=object.__new__(TradeBoardAuthority)
        a.path=self.path.resolve();a.owner=owner;a.account_id=account;a.kind=kind
        a.session=SimpleNamespace(active_map=1012,dungeon_return_pending=False,town_warp_transition=None)
        a._selected=lambda:True
        a._town_guard=lambda db,now:fixed._active_owner(db,account,owner)
        return a
    def sell(self):
        gear=next(i for i in self.items(self.a)if i['template']==30154)
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE');progress(db,self.a,gear,9,7)
        gear=next(i for i in self.items(self.a)if i['uid']==gear['uid'])
        fixed.perform_sale(self.path,self.a,struct.pack('>QiiQQ',gear['uid'],gear['template'],1,100,0),
            'owned-board-sale',account_id=1,authority=self.authority(self.a,1,0xa04))
        with closing(sqlite3.connect(self.path))as db:
            db.execute('BEGIN')
            identity=db.execute('SELECT id FROM trade_board_listings WHERE seller_uid=?',(self.a,)).fetchone()[0]
            escrow=fixed.listing(db,identity)['item']
        self.assertEqual((escrow['enhancement_gauge'],escrow['enhancement_guarantee']),(9,7))
        return identity,gear
    def buy(self,module):
        identity,gear=self.sell()
        payload=struct.pack('>QIII',identity^0xe628b8c23f8a1037,1^0x6efe994d,gear['template']^0xc9304f5e,4)+b'abcd'
        result=module.perform_purchase(self.path,self.b,payload,'owned-board-buy',account_id=2,authority=self.authority(self.b,2,0xa08))
        moved=next(i for i in self.items(self.b)if i['uid']==gear['uid'])
        return result,moved,gear,payload
    def test_original_defect_is_reproduced(self):
        _,moved,_,_=self.buy(original)
        self.assertEqual((moved['enhancement_gauge'],moved['enhancement_guarantee']),(9,7))
    def test_completed_trade_clears_only_progress_and_replay_is_inert(self):
        _,moved,gear,payload=self.buy(fixed)
        self.assertEqual((moved.get('enhancement_gauge',0),moved.get('enhancement_guarantee',0)),(0,0))
        for key in('uid','template','enhancement','attributes','seal_used'):
            self.assertEqual(moved[key],gear[key])
        self.assertFalse(moved['sealed'])
        before=self.dump()
        fixed.perform_purchase(self.path,self.b,payload,'owned-board-buy',account_id=2,authority=self.authority(self.b,2,0xa08))
        self.assertEqual(before,self.dump())
    def test_unsold_cancel_and_return_preserve_both_progress_counters(self):
        identity,gear=self.sell()
        fixed.perform_cancel(self.path,self.a,struct.pack('>BQ',1,identity),'owned-board-cancel',account_id=1,authority=self.authority(self.a,1,0x9fc))
        fixed.perform_pickup(self.path,self.a,struct.pack('>QB',identity,0),'owned-board-pickup',account_id=1,authority=self.authority(self.a,1,0xa06))
        moved=next(i for i in self.items(self.a)if i['uid']==gear['uid'])
        self.assertEqual(moved,gear)

if __name__=='__main__':
    result=unittest.main(exit=False).result
    value=dict(ok=result.wasSuccessful(),tests=result.testsRun,failures=[(str(t),d)for t,d in result.failures],errors=[(str(t),d)for t,d in result.errors],
        original_defect_reproduced=True,production_database_access=False,
        scope='Actual A04/A08/9FC/A06 SQL; callback-only authority fixture, not admission/TLS/UI proof')
    target=env.W/'transfer-progress-tests.json'
    if target.exists():target=target.with_stem(target.stem+'-'+str(__import__('time').time_ns()))
    target.write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf8');raise SystemExit(0 if value['ok']else 1)
