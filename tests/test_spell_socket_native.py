"""Real temp SQL, original requests, conservation, lifecycle and replay guards."""
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import json,sqlite3,struct,tempfile,unittest
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain.equipment_spell_rules import catalog,capacity
from els_server.domain.spell_socket_rules import material,draw
from els_server.domain.acquisition_policy import can_acquire
from els_server.storage import spell_socket as store,spell_socket_pending as pending
from els_server.protocol.spell_socket_messages import request,acknowledgement

def wire(uid,source=0,group=10,slot=0,mode=2):
    return struct.pack('>QIiIiQBiB',uid,1,group,1,slot,source,0,2,0)if mode==2 else struct.pack('>QIBiB',uid,0,0,4,0)

class NativeMysticTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='native-mystic-');self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'game.sqlite3';self.account=LocalAccount(LocalState(self.path));self.account.enable_characters()
        target=next(int(t)for t,row in catalog()['targets'].items()if row['tag64']and int(t)in VERIFIED_TEMPLATES and can_acquire(int(t)))
        self.weapon=self.grant(target);self.stone=self.grant(136109,8)
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('UPDATE reward_balances SET ed=5000000 WHERE uid=1001');db.execute('UPDATE characters SET level=99 WHERE uid=1001')
    def grant(self,t,q=1):
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE');return grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=q)],1001)[0]
    def snapshot(self):
        with closing(sqlite3.connect(self.path))as db:return tuple(db.iterdump())
    def items(self):
        with closing(sqlite3.connect(self.path))as db:return {i['uid']:i for i in load_items(db,1001)}
    def ed(self):
        with closing(sqlite3.connect(self.path))as db:return db.execute('SELECT ed FROM reward_balances WHERE uid=1001').fetchone()[0]
    def perform(self,p=None,op='preview',**kwargs):
        return store.perform(self.path,1001,p or wire(self.weapon['uid'],self.stone['uid']),op,account_id=1,**kwargs)
    def preview(self,op='preview',slot=8):return self.perform(wire(self.weapon['uid'],self.stone['uid'],slot=slot),op,randbelow=lambda n:0)
    def apply(self,op='apply'):return self.perform(wire(self.weapon['uid'],mode=4),op)
    def test_native_ED_UID_order_and_high_uid_writer(self):
        uid=2**48+9001;ed=987654321;e=acknowledgement(uid,ed,mode=2,option=64001001)
        self.assertEqual(struct.unpack_from('>iQQI',e.payload),(0,ed,uid,0))
        self.assertEqual(request(wire(uid,uid+1,slot=8)),(uid,10,8,uid+1,2))
        self.assertEqual(request(wire(uid,mode=4)),(uid,None,None,None,4))
    def test_paid_preview_then_cold_apply_exactly_once(self):
        before=self.items()[self.weapon['uid']];initial=self.ed();reply=self.preview()
        self.assertEqual(self.items()[self.weapon['uid']],before);self.assertEqual(self.ed(),initial-200000)
        self.assertEqual(self.items()[self.stone['uid']]['count'],7)
        option=struct.unpack_from('>i',reply[0].payload,len(reply[0].payload)-12)[0]
        with closing(sqlite3.connect(self.path))as db:self.assertEqual(pending.get(db,1001)['option_id'],option)
        cold=LocalAccount(LocalState(self.path));cold.enable_characters();self.assertEqual(cold.get_inventory_snapshot()['items'],list(self.items().values()))
        self.apply();self.assertEqual(self.items()[self.weapon['uid']]['option_groups']['10'][8],option)
        self.assertEqual(self.ed(),initial-200000);self.assertEqual(self.items()[self.stone['uid']]['count'],7)
        before=self.snapshot();self.apply();self.assertEqual(self.snapshot(),before)
        self.perform(wire(self.weapon['uid'],self.stone['uid'],slot=8),op='preview',randbelow=lambda n:self.fail('old paid generation redrew'))
        self.assertEqual(self.snapshot(),before)
    def test_missing_preview_and_foreign_target_rejected(self):
        before=self.snapshot()
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(self.snapshot(),before);self.preview();before=self.snapshot()
        with self.assertRaises(ValueError):self.perform(wire(self.stone['uid'],mode=4),'foreign-target')
        self.assertEqual(self.snapshot(),before)
    def test_original_color_pool_and_invalid_rng_are_not_mixed(self):
        self.assertEqual(material(136109)['pool_type'],625);self.assertEqual(material(135880)['pool_type'],431)
        for t in (136109,136110,136111,136112):
            self.assertTrue(64000000<=draw(t,lambda n:0)<65000000)
        for v in (-1,True,10**9):
            before=self.snapshot()
            with self.assertRaises(ValueError):self.perform(randbelow=lambda n:v)
            self.assertEqual(self.snapshot(),before)
    def test_lifecycle_guard_precedes_new_and_replayed_operations(self):
        self.preview();self.apply()
        from els_server.storage.character_lifecycle import initialize
        with closing(sqlite3.connect(self.path))as db,db:
            initialize(db);db.execute('INSERT INTO character_lifecycle VALUES (1001,1,1,100,1000,500,0,0)')
        for op,p in [('new',wire(self.weapon['uid'],self.stone['uid'])),('preview',wire(self.weapon['uid'],self.stone['uid'],slot=8)),('apply',wire(self.weapon['uid'],mode=4))]:
            before=self.snapshot()
            with self.assertRaisesRegex(ValueError,'pending deletion'):self.perform(p,op)
            self.assertEqual(self.snapshot(),before)
    def test_insufficient_fee_material_color_and_unknown_actor_conserve_all(self):
        for kwargs,p in [(dict(account_id=2),wire(self.weapon['uid'],self.stone['uid'])),({},wire(self.weapon['uid'],self.stone['uid'],group=11)),({},wire(self.weapon['uid'],self.weapon['uid']))]:
            before=self.snapshot()
            with self.assertRaises(ValueError):store.perform(self.path,1001,p,'bad',account_id=kwargs.get('account_id',1))
            self.assertEqual(self.snapshot(),before)
        with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE reward_balances SET ed=199999 WHERE uid=1001')
        before=self.snapshot()
        with self.assertRaises(ValueError):self.preview()
        self.assertEqual(self.snapshot(),before)
    def test_encoding_receipt_and_late_authority_failure_roll_back(self):
        for kind in ('encode','receipt','authority'):
            before=self.snapshot()
            if kind=='encode':
                with self.assertRaisesRegex(ValueError,'encoder'):self.preview_with_encoder()
            elif kind=='receipt':
                original=store._commit
                def fail(*a,**k):original(*a,**k);raise ValueError('receipt')
                with patch.object(store,'_commit',side_effect=fail):
                    with self.assertRaisesRegex(ValueError,'receipt'):self.preview()
            else:
                count=[0]
                def auth(db):
                    count[0]+=1
                    if count[0]>1:raise ValueError('lease replaced')
                with self.assertRaisesRegex(ValueError,'lease replaced'):self.perform(authorize=auth,randbelow=lambda n:0)
            self.assertEqual(self.snapshot(),before)
    def preview_with_encoder(self):return self.perform(randbelow=lambda n:0,encode=lambda *a,**k:(_ for _ in()).throw(ValueError('encoder')))
    def test_malformed_debug_free_and_wrong_map_never_write(self):
        p=wire(self.weapon['uid'],self.stone['uid'])
        for invalid in (p[:-1],p+b'\0',p[:-6]+b'\1'+p[-5:],p[:-1]+b'\1',wire(self.weapon['uid'],self.stone['uid'],slot=9),wire(self.weapon['uid'],self.stone['uid'],group=12,slot=3)):
            before=self.snapshot()
            with self.assertRaises(ValueError):self.perform(invalid,'bad')
            self.assertEqual(self.snapshot(),before)
    def test_replacing_preview_does_not_revive_old_receipts(self):
        self.preview();self.preview('preview-new',slot=7);before=self.snapshot()
        response=self.preview();self.assertEqual(struct.unpack_from('>i',response[0].payload)[0],2005);self.assertEqual(self.snapshot(),before)
        self.apply();self.preview('preview-third',slot=6);before=self.snapshot();self.apply()
        self.assertEqual(self.snapshot(),before)
    def test_last_stone_preview_and_replay_keep_current_replacement_slot(self):
        with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE inventory_items SET count=1 WHERE uid=?',(self.stone['uid'],))
        self.preview();self.assertNotIn(self.stone['uid'],self.items());replacement=self.grant(136109)
        self.assertEqual(replacement['slot'],self.stone['slot']);before=self.snapshot();self.preview();self.assertEqual(self.snapshot(),before)
    def test_movement_and_actual_sort_cancel_only_moved_preview(self):
        from els_server.storage.wear_moves import move
        from els_server.storage.inventory_management import sort_category_inventory
        import uuid
        self.preview();item=self.items()[self.weapon['uid']]
        sort_category_inventory(self.path,1001,struct.pack('>i',1),'no-op-sort')
        with closing(sqlite3.connect(self.path))as db:self.assertIsNotNone(pending.get(db,1001))
        session=str(uuid.uuid4());destination=item['slot']+10
        move(self.path,struct.pack('>BiBiB',item['group'],item['slot'],item['group'],destination,0),1001,account_id=1,session_id=session,sequence=1)
        move(self.path,struct.pack('>BiBiB',item['group'],destination,item['group'],item['slot'],0),1001,account_id=1,session_id=session,sequence=2)
        with closing(sqlite3.connect(self.path))as db:self.assertIsNone(pending.get(db,1001))
        before=self.snapshot()
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(self.snapshot(),before)
    def test_optional_read_has_no_DDL_and_foreign_owner_keeps_pending(self):
        with closing(sqlite3.connect(self.path))as db:
            before=tuple(db.iterdump());self.assertIsNone(pending.get(db,1001));self.assertEqual(tuple(db.iterdump()),before)
        self.preview()
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE');pending.cancel(db,1002,[self.weapon['uid']]);self.assertIsNotNone(pending.get(db,1001))

if __name__=='__main__':unittest.main()
