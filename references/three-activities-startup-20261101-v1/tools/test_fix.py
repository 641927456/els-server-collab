"""Focused regression: official rewards, economic atomicity and lifecycle."""
from pathlib import Path
from contextlib import closing
from collections import Counter
from unittest.mock import patch
import asyncio,hashlib,json,sqlite3,struct,sys,tempfile,unittest
HOME=Path(__file__).resolve().parent;ROOT=HOME/'runtime';sys.path.insert(0,str(ROOT))
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.domain.local_session import LocalAccount
import els_server;assert Path(els_server.__file__).resolve().is_relative_to(Path(__file__).resolve().parent/'runtime'),els_server.__file__
from els_server.storage.local_state import LocalState
from els_server.domain.owned_growth_items import install
from els_server.domain.boosting_2026_chain_items import register_verified
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,item_body
from els_server.storage.inventory_state import grant_items,load_items,InventoryFull
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.domain.tenebros_capacity_flow import selected
from els_server.storage.fixed_cubes import open_cube
from els_server.storage import bank_state
from els_server.domain.boosting_2026_item_policy import EVENT_ITEMS,deadline
install();register_verified((ROOT/'els_server/data/selected2026/growth-growth_chain_items.json').read_bytes())
EXPECTED={723619:{710128:30,118653:30},723620:{723622:5,723623:5,723624:5,723625:5},
    723621:{30675:1,30676:1,30677:1},723634:{30770:1,30771:1,30772:1,30773:1,30832:1}}
RECORDS=[]
def wire(uid,choices=(),count=1):
    return struct.pack('>QBBBI',uid,0,0,0,len(choices))+b''.join(struct.pack('>i',t)for t in choices)+struct.pack('>i',count)

class Fix(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='fix-fixture-',dir=HOME);self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'synthetic.sqlite3';self.root=LocalAccount(LocalState(self.path));self.root.enable_characters()
        self.uid=self.root.characters.create('FixOwner',1,'fix-owner')['uid'];self.other=self.root.characters.create('FixOther',5,'fix-other')['uid']
        self.account=self.root.for_character(self.uid);self.account.get_inventory_snapshot();self.root.for_character(self.other).get_inventory_snapshot()
        from els_server.domain.character_rules import CLASSES
        from els_server.game_data import client_data
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('UPDATE characters SET unit_type=?,unit_class=150,level=99,transcendence=?,master=0 WHERE uid=?',
                (client_data().unit(150)['unitType'],int(CLASSES[150]['stage']==3),self.uid))
        self.app=Application(ServerConfig(state_file=self.path));self.app.account=self.root;self.addCleanup(self.app.executor.shutdown,wait=True)
        self.s=asyncio.run(self.app.session());self.s.account=self.account;self.s.role='game';self.s.phase='town_ready';self.s.active_map=20001
        self.s.completed.update((0x28,0x225,0x227));self.prepare=selected(self.s)[3]
    def items(self,uid=None):
        with closing(sqlite3.connect(self.path))as db:return load_items(db,self.uid if uid is None else uid)
    def grant(self,t,count=1,expires=None):
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE');self.prepare(db)
            row=dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=count)
            if expires is not None:row['expires_at']=expires
            return grant_items(db,[row],self.uid)[0]
    def snapshot(self):
        with closing(sqlite3.connect(self.path))as db:
            tables={r[0]for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            rows=[(t,list(db.execute('SELECT * FROM '+t+' ORDER BY 1')))for t in('inventory_items','reward_balances','inventory_action_receipts','raid_reward_sources','item_expiration','expired_item_receipts','shared_bank_items','private_bank_items')if t in tables and db.execute('SELECT 1 FROM '+t+' LIMIT 1').fetchone()]
            return hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()
    def use(self,box,sequence,choices=(),count=1):
        return self.s.handle(Event(0x202,performers=(0,),kind=0x196,payload=wire(box['uid'],choices,count)),sequence)
    def ack(self,events,kind=0x197):return next(e for e in events if e.kind==kind)
    def direct(self,box,op,choices=(),count=1):
        return open_cube(self.path,self.uid,box['template'],wire(box['uid'],choices,count),op,account_id=self.account.account_id,prepare=self.prepare)
    def cold(self):
        account=LocalAccount(LocalState(self.path,self.uid));account.enable_characters()
        self.assertEqual(account.get_inventory_snapshot()['items'],self.items())
    def test_four_boxes_actual_handler_exact_outputs_replay_cold(self):
        for n,(t,expected)in enumerate(EXPECTED.items()):
            box=self.grant(t);before=Counter({})
            for i in self.items():before[i['template']]+=i['count']
            foreign=self.items(self.other);ed=self.account.get_reward_balances()['ed']
            preview=self.s.handle(Event(0x202,performers=(0,),kind=0x559,payload=struct.pack('>iIiBB',t,1,0,0,0)),100+n*3)
            self.assertEqual(struct.unpack_from('>i',self.ack(preview,0x55a).payload)[0],0)
            response=self.use(box,101+n*3);self.assertEqual(struct.unpack_from('>i',self.ack(response).payload)[0],0)
            for e in preview+response:encode_event(e)
            after=Counter()
            for i in self.items():after[i['template']]+=i['count']
            self.assertEqual(dict(after-before),expected);self.assertEqual(before-after,Counter({t:1}))
            self.assertEqual(self.items(self.other),foreign);self.assertEqual(self.account.get_reward_balances()['ed'],ed)
            self.assertFalse(any(i['uid']==box['uid']for i in self.items()))
            saved=self.snapshot();self.use(box,101+n*3);self.assertEqual(saved,self.snapshot());self.cold()
            RECORDS.append(dict(template=t,outputs=expected,handler=True,replay=True,cold=True))
    def test_wrong_choice_bulk_and_full_bag_have_no_economic_delta(self):
        box=self.grant(723619)
        for choice,count in(((710128,),1),((),2)):
            before=self.snapshot()
            with self.assertRaises(ValueError):self.direct(box,'bad-choice-or-count:'+str(count),choice,count)
            self.assertEqual(before,self.snapshot())
        from els_server.storage.bag_capacity import allowances
        # A valid full bag: opening frees one source slot but needs two output
        # stacks. The second grant must roll back the first grant and debit.
        with closing(sqlite3.connect(self.path))as db,db:
            occupied={i['slot']for i in load_items(db,self.uid)if i['group']==4}
            from els_server.storage.item_instances import next_uid
            for slot in range(allowances(db,self.uid)[4]):
                if slot not in occupied:db.execute('INSERT INTO inventory_items VALUES (?,?,?,?,?,?,?)',
                    (next_uid(db),self.uid,710085,VERIFIED_TEMPLATES[710085],1,4,slot))
        before=self.snapshot()
        with self.assertRaises(InventoryFull):self.direct(box,'full-bag')
        self.assertEqual(before,self.snapshot())
    def test_late_encode_failure_rolls_back_source_debit_and_grants(self):
        box=self.grant(723621);before=self.snapshot()
        with patch('els_server.protocol.protocol_codec.encode_event',side_effect=ValueError('injected encoding failure')):
            with self.assertRaisesRegex(ValueError,'injected'):self.direct(box,'late-encode')
        self.assertEqual(before,self.snapshot())
    def test_new_reward_reader_cannot_be_granted_without_box_authority(self):
        before=self.snapshot()
        with self.assertRaises(ValueError):self.grant(710128)
        self.assertEqual(before,self.snapshot())
    def test_shared_bank_ban_private_allowed_and_swap_checked(self):
        from els_server.domain.bank_rules import require_storable
        for t in EVENT_ITEMS:
            with self.assertRaisesRegex(ValueError,'event items'):require_storable(dict(template=t,group=4),16)
        box=self.grant(723680)
        packet=lambda sg,ss,dg,ds,n,t:struct.pack('>BiBiiQi',sg,ss,dg,ds,n,0,t)
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'event items'):bank_state.transfer(self.path,self.uid,packet(4,box['slot'],16,0,1,723680),'blocked-deposit')
        self.assertEqual(before,self.snapshot())
        bank_state.transfer(self.path,self.uid,packet(4,box['slot'],8,0,1,723680),'private-deposit')
        bank_state.transfer(self.path,self.uid,packet(8,0,4,box['slot'],1,723680),'private-withdraw')
        ordinary=self.grant(710085)
        bank_state.transfer(self.path,self.uid,packet(4,ordinary['slot'],16,0,1,710085),'ordinary-shared')
        before=self.snapshot()
        # Withdraw ordinary into occupied event slot: the displaced event box
        # would enter the shared bank and must be rejected as well.
        with self.assertRaisesRegex(ValueError,'event items'):bank_state.transfer(self.path,self.uid,packet(16,0,4,box['slot'],1,710085),'blocked-swap')
        self.assertEqual(before,self.snapshot())
    def test_legacy_missing_deadline_and_new_grants_expire_at_event_end(self):
        from els_server.domain.item_expiration import expired
        from els_server.storage.item_expiration import remove_due
        box=self.grant(723635)
        with closing(sqlite3.connect(self.path))as db,db:
            self.assertEqual(db.execute('SELECT expires_at FROM item_expiration WHERE item_uid=?',(box['uid'],)).fetchone(),(deadline(),))
            db.execute('DELETE FROM item_expiration WHERE item_uid=?',(box['uid'],))
        legacy=next(i for i in self.items()if i['uid']==box['uid']);self.assertEqual(legacy['expires_at'],deadline())
        self.assertFalse(expired(legacy,now=deadline()));self.assertTrue(expired(legacy,now=deadline()+1))
        before=self.snapshot()
        with patch('time.time',return_value=deadline()+1):
            with self.assertRaises(ValueError):self.direct(box,'expired-open')
        self.assertEqual(before,self.snapshot())
        saved=self.snapshot()
        with patch('els_server.protocol.expiration_messages.notice',side_effect=ValueError('expiry encoding failure')):
            with self.assertRaises(ValueError):remove_due(self.path,self.uid,now=deadline()+1)
        self.assertEqual(saved,self.snapshot())
        messages=remove_due(self.path,self.uid,now=deadline()+1);self.assertTrue(messages)
        self.assertFalse(any(i['uid']==box['uid']for i in self.items()))
        self.assertEqual(remove_due(self.path,self.uid,now=deadline()+1),[]);self.cold()
    def test_ninety_day_outputs_keep_lifetime_and_old_early_deadlines_are_not_extended(self):
        from els_server.domain.item_expiration import expired
        early=deadline()-3600;box=self.grant(723635,expires=early)
        self.assertEqual(box['expires_at'],early)
        fashion=self.grant(721780);response=self.use(fashion,400)
        self.assertEqual(struct.unpack_from('>i',self.ack(response).payload)[0],0)
        timed=[i for i in self.items()if i['group']==27 and 'expires_at'in i]
        self.assertEqual(len(timed),11)
        for i in timed:
            self.assertGreater(i['expires_at'],deadline())
            self.assertFalse(expired(i,now=deadline()+1))
        self.cold()

if __name__=='__main__':
    suite=(unittest.defaultTestLoader.loadTestsFromNames(['Fix.'+n for n in sys.argv[1:]],module=sys.modules[__name__])
        if len(sys.argv)>1 else unittest.defaultTestLoader.loadTestsFromTestCase(Fix))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    out=dict(ok=result.wasSuccessful(),tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),records=RECORDS,
        layer='Application-owned LocalSession and isolated real SQLite transactions',natural_GUI=False,production_changed=False)
    (HOME/'fix-test-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    sys.exit(0 if result.wasSuccessful()else 1)
