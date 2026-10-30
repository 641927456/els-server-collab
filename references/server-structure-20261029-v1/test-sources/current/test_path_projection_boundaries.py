from contextlib import closing,contextmanager
from pathlib import Path
import json,os,sqlite3,struct,tempfile,time,unittest,uuid
from types import MethodType
from unittest.mock import patch

from els_server.storage.read_scope import checked_paths,committed_reads,role_projection
from els_server.storage.sqlite_timing import write_transaction
from els_server.performance import worker_timing
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage import bank_state as bank,wardrobe
from els_server.storage.inventory_state import grant_items,load_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS

ROOT=Path(__file__).resolve().parents[1]


class ClosedPathTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(dir=ROOT);self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name);self.path=self.root/'owned.sqlite';self.path.write_bytes(b'owned')

    def test_duplicate_names_resolve_once_then_recheck_at_end(self):
        original=Path.resolve;seen=[]
        def record(path,*args,**kwargs):seen.append(path);return original(path,*args,**kwargs)
        with patch.object(Path,'resolve',record):
            with checked_paths()as resolve:
                self.assertEqual(resolve(self.path),self.path)
                self.assertEqual(resolve(str(self.path)),self.path)
                self.assertEqual(resolve(self.path),self.path)
            self.assertEqual(len(seen),2)

    def test_new_check_never_reuses_prior_resolution(self):
        original=Path.resolve;seen=[]
        def record(path,*args,**kwargs):seen.append(path);return original(path,*args,**kwargs)
        with patch.object(Path,'resolve',record):
            for _ in range(2):
                with checked_paths()as resolve:resolve(self.path)
        self.assertEqual(len(seen),4)

    def test_atomic_replacement_refused_even_with_same_filename(self):
        replacement=self.root/'replacement.sqlite';replacement.write_bytes(b'other')
        with self.assertRaisesRegex(ValueError,'path changed'):
            with checked_paths()as resolve:
                resolve(self.path)
                os.replace(replacement,self.path)
                self.assertEqual(resolve(self.path),self.path)

    def test_ordinary_same_file_writes_do_not_revoke_path(self):
        with checked_paths()as resolve:
            resolve(self.path)
            self.path.write_bytes(b'ordinary same-file update')

    def test_distinct_aliases_are_canonicalized_independently(self):
        (self.root/'sub').mkdir()
        with checked_paths()as resolve:
            self.assertEqual(resolve(self.root/'sub/../owned.sqlite'),resolve(self.path))

    def test_body_denial_is_not_masked_by_end_check(self):
        with self.assertRaisesRegex(ValueError,'original denial'):
            with checked_paths()as resolve:
                resolve(self.path);self.path.unlink();raise ValueError('original denial')


class OwnedDatabase(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(dir=ROOT);self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/'owned.sqlite'
        self.account=LocalAccount(LocalState(self.path));self.account.enable_characters();self.account.enable_inventory()


class ProjectionTests(OwnedDatabase):
    def test_identity_reuses_only_original_same_generation_full_view(self):
        with committed_reads():
            full=self.account.character();wanted={k:full[k]for k in('uid','name','unit_type','unit_class','level','transcendence','master','revision','account_id')}
            full['level']=99
            with patch('els_server.storage.read_scope.snapshot_connection',side_effect=AssertionError('unexpected identity SQL')):
                identity=self.account.character_identity();self.assertEqual(identity,wanted)
                identity['level']=77
                self.assertEqual(self.account.character_identity(),wanted)

    def test_external_commit_invalidates_derived_identity(self):
        with committed_reads():
            self.account.character();self.assertEqual(self.account.character_identity()['level'],1)
            with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE characters SET level=99 WHERE uid=1001')
            self.assertEqual(self.account.character_identity()['level'],99)

    def test_owner_revocation_still_rejects_after_cached_full(self):
        with committed_reads():
            self.account.character()
            with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE character_owners SET account_id=2 WHERE uid=1001')
            with self.assertRaises(ValueError):self.account.character_identity()

    def test_finalized_deletion_still_rejects_after_cached_full(self):
        from els_server.storage.character_lifecycle import initialize
        with committed_reads():
            self.account.character()
            with closing(sqlite3.connect(self.path))as db,db:
                initialize(db)
                db.execute('INSERT OR REPLACE INTO character_lifecycle(uid,account_id,created_at,finalized_at)VALUES(1001,1,0,1)')
            with self.assertRaises(ValueError):self.account.character_identity()

    def test_untrusted_full_callback_cannot_seed_identity(self):
        original=self.account.character()
        with committed_reads():
            role_projection(self.account,lambda:dict(original,level=77))
            self.assertEqual(self.account.character_identity()['level'],1)

    def test_instance_custom_full_reader_cannot_seed_identity(self):
        original=self.account.character()
        self.account._character_projection=MethodType(lambda actor:dict(original,level=77),self.account)
        with committed_reads():
            self.account.character()
            self.assertEqual(self.account.character_identity()['level'],1)

    def test_instance_custom_character_get_cannot_seed_identity(self):
        original=self.account.character()
        self.account.characters.get=lambda uid:dict(original,level=77)
        with committed_reads():
            self.account.character()
            self.assertEqual(self.account.character_identity()['level'],1)

    def test_custom_identity_reader_preserves_its_original_behavior(self):
        self.account.characters.identity=lambda uid:dict(uid=uid,level=55,custom=True)
        with committed_reads():
            self.account.character()
            self.assertTrue(self.account.character_identity()['custom'])

    def test_live_local_authority_is_not_cached_by_path_work(self):
        from els_server.application import Application
        from els_server.config import ServerConfig
        from els_server.domain.equipment_chip_flow import reset_authority
        app=Application(ServerConfig(mode='local',profile='bootstrap',state_file=self.path));self.addCleanup(app.close);app.account=self.account
        session=LocalSession(self.account);session._chip_reset_local_application=app;session._chip_reset_local_live=True
        reset_authority(session)
        session._chip_reset_local_live=False
        with self.assertRaises(ValueError):reset_authority(session)


class StorageWriterTests(OwnedDatabase):
    def grant(self):
        with closing(sqlite3.connect(self.path))as db,db:
            return grant_items(db,[dict(template=77420,quantity=4,metadata=VERIFIED_TEMPLATES[77420],group=TEMPLATE_BAG_GROUPS[77420])],1001)[0]

    def transfer(self,item,group=8):
        return struct.pack('>BiBiiQi',item['group'],item['slot'],group,0,2,0,item['template'])

    def amount(self):
        with closing(sqlite3.connect(self.path))as db:
            return sum(i['count']for i in load_items(db,1001)if i['template']==77420),sum(e['item']['count']for e in bank.load(db,1001)if e['item']['template']==77420)

    def test_idle_bank_read_does_not_wait_for_reserved_writer(self):
        with closing(sqlite3.connect(self.path))as writer:
            writer.execute('BEGIN IMMEDIATE');sample={}
            with worker_timing(sample),committed_reads():self.assertEqual(bank.remove_due(self.path,1001),[])
            self.assertEqual(sample.get('sql_begin_wait_ms',0),0)
            writer.rollback()

    def test_bank_transfer_rollback_then_replay_keeps_exact_quantity(self):
        item=self.grant();payload=self.transfer(item);operation=str(uuid.uuid4())
        with patch('els_server.storage.bank_state.transfer_ack',side_effect=ValueError('encode')),self.assertRaisesRegex(ValueError,'encode'):
            bank.transfer(self.path,1001,payload,operation)
        self.assertEqual(self.amount(),(4,0))
        bank.transfer(self.path,1001,payload,operation);self.assertEqual(self.amount(),(2,2))
        bank.transfer(self.path,1001,payload,operation);self.assertEqual(self.amount(),(2,2))

    def test_bank_preview_ends_before_writer_and_rechecks_expiration(self):
        item=self.grant();bank.transfer(self.path,1001,self.transfer(item),str(uuid.uuid4()))
        with closing(sqlite3.connect(self.path))as db,db:
            row=db.execute('SELECT uid,item_json FROM private_bank_items').fetchone();value=json.loads(row[1]);value['expires_at']=int(time.time())-1
            db.execute('UPDATE private_bank_items SET item_json=? WHERE uid=?',(json.dumps(value),row[0]))
        @contextmanager
        def refreshed(db):
            with closing(sqlite3.connect(self.path,timeout=.02))as other,other:
                value['expires_at']=int(time.time())+3600
                other.execute('UPDATE private_bank_items SET item_json=? WHERE uid=?',(json.dumps(value),row[0]))
            with write_transaction(db):yield db
        with patch('els_server.storage.bank_state.write_transaction',refreshed),committed_reads():self.assertEqual(bank.remove_due(self.path,1001),[])
        self.assertEqual(self.amount(),(2,2))

    def test_bank_begin_contention_before_any_transfer_sort_expansion(self):
        item=self.grant();connect=sqlite3.connect
        def short(*args,**kwargs):kwargs['timeout']=.02;return connect(*args,**kwargs)
        calls=(lambda:bank.transfer(self.path,1001,self.transfer(item),str(uuid.uuid4())),
            lambda:bank.sort(self.path,1001,struct.pack('>i',8),str(uuid.uuid4())),
            lambda:bank.expand(self.path,1001,8,b'',str(uuid.uuid4()),expected=(8,4000000)))
        with closing(connect(self.path))as writer:
            writer.execute('BEGIN IMMEDIATE')
            for call in calls:
                sample={}
                with patch.object(sqlite3,'connect',short),self.assertRaises(sqlite3.OperationalError),worker_timing(sample):call()
                self.assertEqual(sample['sql_busy'],1);self.assertEqual(sample['sql_finish_busy'],0)
            writer.rollback()
        self.assertEqual(self.amount(),(4,0))

    def test_bank_commit_contention_rolls_back_before_retry(self):
        item=self.grant();payload=self.transfer(item);operation=str(uuid.uuid4());connect=sqlite3.connect
        def short(*args,**kwargs):kwargs['timeout']=.02;return connect(*args,**kwargs)
        with closing(connect(self.path))as reader:
            reader.execute('BEGIN');reader.execute('SELECT * FROM inventory_items').fetchall();sample={}
            with patch.object(sqlite3,'connect',short),self.assertRaises(sqlite3.OperationalError),worker_timing(sample):bank.transfer(self.path,1001,payload,operation)
            self.assertEqual(sample['sql_busy'],1);self.assertEqual(sample['sql_finish_busy'],1);reader.rollback()
        self.assertEqual(self.amount(),(4,0));bank.transfer(self.path,1001,payload,operation);self.assertEqual(self.amount(),(2,2))

    def favorite(self):
        from els_server.domain.wardrobe import catalog
        template=next(iter(catalog()))
        return struct.pack('>ii',1,template)

    def test_wardrobe_late_denial_and_replay_remain_atomic(self):
        payload=self.favorite();operation=str(uuid.uuid4());calls=0
        def guard():
            nonlocal calls
            calls+=1
            if calls==2:raise ValueError('late lease')
        with self.assertRaisesRegex(ValueError,'late lease'):wardrobe.change(self.path,1001,1,0xbee,payload,operation,validate=guard)
        with closing(sqlite3.connect(self.path))as db:self.assertEqual(wardrobe.favorites(db,1001,1),[])
        first=wardrobe.change(self.path,1001,1,0xbee,payload,operation)
        again=wardrobe.change(self.path,1001,1,0xbee,payload,operation)
        self.assertEqual(first,again)

    def test_both_wardrobe_writers_observe_begin_contention(self):
        connect=sqlite3.connect
        def short(*args,**kwargs):kwargs['timeout']=.02;return connect(*args,**kwargs)
        payload=self.favorite()
        calls=(lambda:wardrobe.change(self.path,1001,1,0xbee,payload,str(uuid.uuid4())),
            lambda:wardrobe.extension_change(self.path,1001,1,0x4f4,struct.pack('>iQ',1,1),str(uuid.uuid4()),validate=lambda:None))
        with closing(connect(self.path))as writer:
            writer.execute('BEGIN IMMEDIATE')
            for call in calls:
                sample={}
                with patch.object(sqlite3,'connect',short),self.assertRaises(sqlite3.OperationalError),worker_timing(sample):call()
                self.assertEqual(sample['sql_busy'],1)
            writer.rollback()
