"""Synthetic G: saves exercise the original App worker and mail transactions."""
from pathlib import Path
from contextlib import closing
from collections import Counter
import asyncio,gc,json,os,sqlite3,struct,sys,tempfile,time,unittest

ROOT=Path(__file__).resolve().parents[2]
BASE=Path(os.environ['ELS_RETAINED_MAIL_RUNTIME']).resolve()
OUT=Path(os.environ['ELS_RETAINED_MAIL_TEST_HOME']).resolve();OUT.mkdir(parents=True,exist_ok=True)
SOURCE=Path(__file__).resolve().parent/'source/els_server'
sys.dont_write_bytecode=True
sys.path[:0]=[str(BASE),str(BASE/'tools'),str(ROOT/'tools')]
import els_server.domain,els_server.storage,els_server.protocol
for module,name in ((els_server.domain,'domain'),(els_server.storage,'storage'),(els_server.protocol,'protocol')):
    module.__path__.insert(0,str(SOURCE/name))
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.storage.accounts import Accounts
from els_server.storage import game_mail,mail_attachments
from els_server.storage.inventory_state import load_items,grant_items
from els_server.domain.retained_native_consumables import definitions,read_existing,validate_existing
from els_server.domain.inventory_items import validate_item,item_body,TEMPLATE_MAX_STACKS,VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.protocol import mail_attachment_messages as wire
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.domain.online_2026_mail_notice import OnlineMailNotice,MailNoticePolicy


class MailLoginTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='owned-mail-',dir=OUT)
        self.path=Path(self.temp.name)/'game.sqlite3';self.runner=asyncio.Runner()
        self.account=LocalAccount(LocalState(self.path));self.account.enable_characters()
        config=ServerConfig(state_file=self.path,log_dir=self.path.parent/'logs',mode='friends',
            accounts_file=self.path.parent/'accounts.sqlite3',tls_cert=self.path.parent/'cert',tls_key=self.path.parent/'key')
        self.app=Application(config);self.app.account=self.account
        self.app.registry=Accounts(config.accounts_file);self.identity=self.app.registry.create('owned_mail')
        self.aid=self.identity['id'];self.account.account_id=self.aid;self.account.characters.account_id=self.aid
        self.app.accounts[self.aid]=self.account
        self.account.get_inventory_snapshot()
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('UPDATE character_owners SET account_id=? WHERE uid=1001',(self.aid,))
            db.execute('UPDATE characters SET unit_type=5,unit_class=164,level=99,transcendence=1,master=0 WHERE uid=1001')
        game_mail.initialize(self.path)
        from els_server.domain.selected_2026_friends import install
        install(self.app)
        self.now=int(time.time());self.counter=0

    def tearDown(self):
        self.app.close();self.runner.close();gc.collect();self.temp.cleanup()

    def dump(self):
        with closing(sqlite3.connect(self.path))as db:return tuple(db.iterdump())

    def mail(self,template=723610,count=3,**overrides):
        self.counter+=1;r=definitions().get(template)or dict(metadata=VERIFIED_TEMPLATES[template],group=TEMPLATE_BAG_GROUPS[template])
        item=dict(uid=900000+self.counter,template=template,metadata=r['metadata'],count=count,group=r['group'],slot=0,
            expires_at=self.now+86400,lock_until=self.now-1)
        item.update(overrides);raw=json.dumps(item,sort_keys=True)
        with closing(sqlite3.connect(self.path))as db,db:
            mid=db.execute('INSERT INTO game_mail(campaign,account_id,sender,title,body,ed,created_at,expires_at) VALUES(?,?,?,?,?,0,?,?)',
                ('owned-old-mail-'+str(self.counter),self.aid,'Fixture','Old attachment','Synthetic retained escrow',self.now,self.now+86400)).lastrowid
            db.execute('INSERT INTO player_mail_items(mail_id,item_uid,source_json,item_json,expires_at) VALUES(?,?,?,?,?)',
                (mid,item['uid'],raw,raw,item.get('expires_at')))
        return mid,item

    def claim(self,mid,encode=None,account=None):
        encode=encode or (lambda ids,ed,changes,counts:wire.claim_ack(ids,ed,changes,counts=counts))
        return game_mail.claim(self.path,self.aid if account is None else account,1001,[mid],encode,now=self.now,
            include_items=True,include_claim_counts=True)

    def inventory(self):
        with closing(sqlite3.connect(self.path))as db:return load_items(db,1001)

    def login(self):
        s=self.runner.run(self.app.session(identity=self.identity));s.role='game';s.phase='characters_ready'
        messages=[]
        for sequence,(kind,payload)in enumerate(((0x28,struct.pack('>Q',1001)),(0x6e9,b''),(0x5bf,bytes(8)),
                (50,b''),(0x225,struct.pack('>iB',20000,0)),(0x227,struct.pack('>fffBH',0,0,0,0,0))),30):
            replies=self.runner.run(self.app.call(s.handle,Event(0x202,kind=kind,payload=payload,performers=(0,)),request_sequence=sequence))
            for event in replies:encode_event(event)
            messages.extend(replies)
        self.assertEqual(s.phase,'town_ready')
        return s,messages

    def test_original_login_and_reconnect_with_unread_retained_attachment(self):
        mid,item=self.mail();s,messages=self.login()
        self.assertTrue(any(e.kind==0x1ce for e in messages))
        self.assertTrue(any(e.kind==0x228 for e in messages))
        with closing(sqlite3.connect(self.path))as db:
            row=db.execute('SELECT claimed_at,item_json FROM player_mail_items WHERE mail_id=?',(mid,)).fetchone()
            self.assertIsNone(row[0]);self.assertEqual(json.loads(row[1]),item)
        self.runner.run(self.app.release(s))
        _,again=self.login();self.assertTrue(any(e.kind==0x1ce for e in again))

    def test_readonly_preview_detail_claim_cold_read_and_replay(self):
        mid,item=self.mail();before=self.dump();messages=[]
        OnlineMailNotice().synchronize(self.path,account=self.aid,character=1001,now=self.now,policy=MailNoticePolicy(False,10),emit=messages.append)
        self.assertEqual([e.kind for e in messages],[0x1ce]);self.assertEqual(self.dump(),before)
        count,rows=game_mail.inbox(self.path,self.aid,1001,now=self.now)
        self.assertEqual(count,1);self.assertEqual(dict(rows[0]['item']),item);wire.list_ack(rows,count)
        game_mail.read(self.path,self.aid,1001,mid,wire.read_ack,now=self.now)
        self.claim(mid)
        restored=next(i for i in self.inventory()if i['uid']==item['uid'])
        self.assertEqual(restored['count'],item['count']);self.assertEqual(restored['expires_at'],item['expires_at'])
        validate_existing(restored);item_body(restored)
        before=self.dump();self.claim(mid);self.assertEqual(self.dump(),before)
        cold=LocalAccount(LocalState(self.path),self.aid);cold.enable_characters()
        self.assertEqual(next(i for i in cold.get_inventory_snapshot()['items']if i['uid']==item['uid']),restored)

    def test_merge_and_remainder_keep_exact_quantity(self):
        mid,item=self.mail();maximum=TEMPLATE_MAX_STACKS[item['template']]
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('INSERT INTO inventory_items VALUES(?,?,?,?,?,?,?)',(800001,1001,item['template'],item['metadata'],maximum-1,item['group'],30))
            from els_server.storage.item_expiration import assign
            from els_server.storage.item_locks import assign as lock
            assign(db,1001,800001,item['expires_at']);lock(db,1001,800001,item['lock_until'])
        self.claim(mid)
        rows=[i for i in self.inventory()if i['template']==item['template']]
        self.assertEqual(sum(i['count']for i in rows),maximum+2)
        self.assertEqual(next(i['count']for i in rows if i['uid']==800001),maximum)
        self.assertEqual(next(i['count']for i in rows if i['uid']==item['uid']),2)
        before=self.dump();self.claim(mid);self.assertEqual(self.dump(),before)

    def test_encoder_failure_rolls_back_and_retry_claims_once(self):
        mid,item=self.mail();before=self.dump()
        def fail(*args):raise ValueError('injected encoding failure')
        with self.assertRaisesRegex(ValueError,'injected encoding failure'):self.claim(mid,fail)
        self.assertEqual(self.dump(),before);self.claim(mid)
        self.assertEqual(sum(i['count']for i in self.inventory()if i['template']==item['template']),3)

    def test_forged_items_generic_grants_and_foreign_account_rejected(self):
        mid,item=self.mail();before=self.dump()
        with self.assertRaises(ValueError):validate_item(item)
        with self.assertRaises(ValueError):self.claim(mid,account=self.aid+1)
        with self.assertRaises(ValueError):
            with closing(sqlite3.connect(self.path))as db,db:
                db.execute('BEGIN IMMEDIATE');grant_items(db,[dict(template=item['template'],metadata=item['metadata'],group=item['group'],quantity=1)],1001)
        self.assertEqual(self.dump(),before)

    def test_corrupt_escrow_and_expired_attachment(self):
        mid,item=self.mail(metadata=9);before=self.dump()
        with self.assertRaises(ValueError):
            with closing(sqlite3.connect(self.path))as db:mail_attachments.pending(db,mid,now=self.now)
        self.assertEqual(self.dump(),before)
        mid,item=self.mail(expires_at=self.now-1)
        with closing(sqlite3.connect(self.path))as db:self.assertIsNone(mail_attachments.pending(db,mid,now=self.now))

    def test_singleton_retained_and_ordinary_attachments(self):
        for template,count in ((723618,1),(710022,3)):
            with self.subTest(template=template):
                mid,item=self.mail(template,count);count_before=sum(i['count']for i in self.inventory()if i['template']==template)
                messages=[]
                OnlineMailNotice().synchronize(self.path,account=self.aid,character=1001,now=self.now,policy=MailNoticePolicy(False,10),emit=messages.append)
                self.assertEqual([e.kind for e in messages],[0x1ce]);self.claim(mid)
                self.assertEqual(sum(i['count']for i in self.inventory()if i['template']==template)-count_before,count)


if __name__=='__main__':unittest.main(verbosity=2)
