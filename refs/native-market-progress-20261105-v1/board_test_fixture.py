"""Owned SQL exchange properties; admission waiting policy is tested separately."""
from pathlib import Path
import os,sys
from types import SimpleNamespace
BASE=Path(os.environ['ELS_FULL_SOURCE']).resolve()
sys.dont_write_bytecode=True;sys.path[:0]=[str(BASE),str(BASE/'vendor')]
env=SimpleNamespace(W=Path(__file__).resolve().parent)
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

from els_server.protocol.protocol_codec import encode_event


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
