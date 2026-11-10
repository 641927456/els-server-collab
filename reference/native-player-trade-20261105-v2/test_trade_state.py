"""Owned SQL exchange properties; admission waiting policy is tested separately."""
import bootstrap as env
env.W=env.HERE
from contextlib import closing
from pathlib import Path
import copy,json,sqlite3,tempfile,unittest
from els_server.storage.game_schema import prepare
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.domain.local_session import LocalAccount
from els_server.storage.inventory_state import grant_items,load_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.storage.item_seals import assign
from els_server.storage.equipment_attributes import replace_attributes
from els_server.storage.equipment_enhancement import replace as enhancement
from els_server.storage.npc_trade import balances
from els_server.protocol import player_trade_messages as wire
from els_server.protocol.protocol_codec import encode_event
from els_server.storage import player_trade_state as state

class ExchangeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='owned-direct-trade-',dir=env.W)
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'own.sqlite3';prepare(self.path);self.owners=[]
        for account,name in((1,'TradeA'),(2,'TradeB')):
            roster=Characters(self.path,account);uid=roster.create(name,account,'own-create-'+name)['uid']
            local=LocalAccount(LocalState(self.path,uid),account_id=account);local.enable_characters(characters=roster);local.get_inventory_snapshot()
            self.owners.append(uid)
            with closing(sqlite3.connect(self.path))as db,db:
                db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,))
                db.execute('UPDATE reward_balances SET ed=5000 WHERE uid=?',(uid,))
                grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=n)
                    for t,n in ((500040,10),(30154,1))]if account==1 else
                    [dict(template=500040,metadata=VERIFIED_TEMPLATES[500040],group=TEMPLATE_BAG_GROUPS[500040],quantity=3)],uid)
        self.a,self.b=self.owners
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE')
            gear=next(i for i in load_items(db,self.a)if i['template']==30154)
            assign(db,self.a,gear['uid'],True,2);replace_attributes(db,self.a,gear['uid'],[0]*4,[1,0,0,0]);enhancement(db,self.a,gear['uid'],0,8)
        self.agreement=dict(id=1,participants=[])
        for account,uid,ed in((1,self.a,101),(2,self.b,20)):
            rows=self.items(uid)
            entries=[dict(item=i,quantity=1 if i['template']==30154 else 4 if account==1 else 1)
                     for i in rows if i['template']in(30154,500040)]
            self.agreement['participants'].append(dict(owner=uid,account=account,generation='own-session-'+str(account),ed=ed,items=entries))

    def tearDown(self):self.temp.cleanup();self.assertFalse(Path(self.temp.name).exists())
    def items(self,uid):
        with closing(sqlite3.connect(self.path))as db:return load_items(db,uid)
    def money(self,uid):
        with closing(sqlite3.connect(self.path))as db:return balances(db,uid)
    def dump(self):
        with closing(sqlite3.connect(self.path))as db:return list(db.iterdump())
    def guard(self,db,now):
        for account,uid in enumerate(self.owners,1):state.require_owner(db,uid,account)
    def encode(self,db,results,repeated):
        events={uid:wire.completed(row['ed'],row['changes'])for uid,row in results.items()}
        for event in events.values():encode_event(event)
        return events
    def run_trade(self,agreement=None,guard=None,encode=None):
        return state.perform(self.path,agreement or self.agreement,'owned-complete-1',guard or self.guard,encode or self.encode)

    def test_bilateral_item_and_fee_exchange_and_replay(self):
        gear=next(i for i in self.items(self.a)if i['template']==30154)
        self.run_trade()
        self.assertEqual((self.money(self.a)['ed'],self.money(self.b)['ed']),(4918,5076))
        self.assertEqual([sum(i['count']for i in self.items(uid)if i['template']==500040)for uid in self.owners],[7,6])
        moved=next(i for i in self.items(self.b)if i['uid']==gear['uid'])
        self.assertEqual({k:v for k,v in moved.items()if k not in('group','slot','sealed')},
                         {k:v for k,v in gear.items()if k not in('group','slot','sealed')})
        self.assertFalse(moved['sealed']);self.assertEqual(moved['seal_used'],2)
        before=self.dump();self.run_trade();self.assertEqual(before,self.dump())
        wrong=copy.deepcopy(self.agreement);wrong['participants'][0]['ed']+=1
        with self.assertRaises(ValueError):self.run_trade(wrong)
        self.assertEqual(before,self.dump())

    def test_late_encoder_and_peer_guard_rollback(self):
        before=self.dump()
        def fail(*args):raise ValueError('Owned response preparation failed')
        with self.assertRaises(ValueError):self.run_trade(encode=fail)
        self.assertEqual(before,self.dump())
        calls=[]
        def stale(db,now):
            self.guard(db,now);calls.append(1)
            if len(calls)>1:raise ValueError('Owned peer changed character')
        with self.assertRaises(ValueError):self.run_trade(guard=stale)
        self.assertEqual(before,self.dump())

    def test_full_recipient_bag_rolls_back_both_owners(self):
        from els_server.storage.bag_capacity import allowances
        with closing(sqlite3.connect(self.path))as db,db:
            free=allowances(db,self.b)[1]-sum(i['group']==1 for i in load_items(db,self.b))
            grant_items(db,[dict(template=30154,metadata=VERIFIED_TEMPLATES[30154],group=1,quantity=free)],self.b)
        before=self.dump()
        with self.assertRaises(ValueError):self.run_trade()
        self.assertEqual(before,self.dump())

    def test_changed_offered_item_and_wallet_capacity_refused(self):
        with closing(sqlite3.connect(self.path))as db,db:
            source=next(i for i in self.items(self.a)if i['template']==500040)
            db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=?',(source['uid'],))
        before=self.dump()
        with self.assertRaises(ValueError):self.run_trade()
        self.assertEqual(before,self.dump())
        for p in self.agreement['participants']:p['items']=[]
        self.agreement['participants'][1]['ed']=0
        from els_server.domain.bank_rules import player_ed_limit
        with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE reward_balances SET ed=? WHERE uid=?',(player_ed_limit(99),self.b))
        before=self.dump()
        with self.assertRaises(ValueError):self.run_trade()
        self.assertEqual(before,self.dump())

    def test_trade_amount_is_distinct_from_wallet_and_progress_resets(self):
        from els_server.storage.enhancement_progress import replace as progress
        gear=next(i for i in self.items(self.a)if i['template']==30154)
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE');progress(db,self.a,gear,9,7)
        for p in self.agreement['participants']:
            p['items']=[dict(item=i,quantity=1)for i in self.items(p['owner'])if i['template']==30154]
        self.run_trade()
        target=next(i for i in self.items(self.b)if i['uid']==gear['uid'])
        self.assertEqual((target.get('enhancement_gauge',0),target.get('enhancement_guarantee',0)),(0,0))
        self.assertEqual(target['enhancement'],8);self.assertEqual(target['attributes'],[1,0,0,0])
        changed=copy.deepcopy(self.agreement);changed['participants'][0]['ed']=10_000_000_001
        # A new economic operation with sufficient wallet must still honor
        # the separate personal-trade cap; the normal positive case above
        # exercised a real equipment transfer and receipt.
        with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE reward_balances SET ed=70000000000 WHERE uid=?',(self.a,))
        before=self.dump()
        with self.assertRaises(ValueError):state.perform(self.path,changed,'owned-cap',self.guard,self.encode)
        self.assertEqual(before,self.dump())

if __name__=='__main__':
    result=unittest.main(exit=False).result
    value=dict(ok=result.wasSuccessful(),tests=result.testsRun,failures=[(str(t),d)for t,d in result.failures],errors=[(str(t),d)for t,d in result.errors],
        production_database_access=False,scope='Two-owner SQL asset settlement only; native admission/waiting policy and TLS flow not claimed')
    target=env.W/'state-tests.json'
    if target.exists():target=target.with_stem(target.stem+'-'+str(__import__('time').time_ns()))
    target.write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf8');raise SystemExit(0 if value['ok']else 1)
