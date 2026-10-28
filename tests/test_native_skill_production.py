"""Producer/selection isolation, rollback and immutable source attribution."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import hashlib,importlib.util,json,struct,sys,threading,unittest
from els_server.protocol.protocol_codec import Event

ROOT=Path(__file__).resolve().parents[1]
A=ROOT/'references/native-server-attributes-20261027-v1'


class SkillProductionTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        import els_server.domain as domain
        self.stack.enter_context(patch.object(domain,'__path__',[str(A/'els_server/domain'),*domain.__path__]))
        self.stack.enter_context(patch.dict(sys.modules))
        for name in('native_skill_delivery_sources','native_attribute_delivery','native_skill_production'):
            spec=importlib.util.spec_from_file_location('els_server.domain.'+name,A/'els_server/domain'/(name+'.py'))
            module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
            self.stack.enter_context(patch.object(domain,name,module,create=True))
        self.port=module;self.delivery=domain.native_attribute_delivery
        self.cursor=self.delivery.DeliveryCursor();self.epoch=self.cursor.begin(1001,2,5)
        self.session=SimpleNamespace(account=SimpleNamespace(uid=1001,account_id=2,
            store=SimpleNamespace(uid=1001)),shop_session_id='controlled-test-token',
            role='game',phase='town_ready',released=False)

    def event(self,kind=0x123):
        return Event(0x201,kind=kind,payload=struct.pack('>5i',0,0,25030,-1,0))

    def capture(self,producer):return self.port.capture(self.epoch,self.session,producer)

    def test_returned_mailbox_equal_clone_and_other_owner_cannot_supply_a_receipt(self):
        event=self.event();equal=self.event();foreign=self.event();unmarked=self.event()
        def produce():
            self.assertIs(self.port.record(event,1001),event)
            self.port.record(foreign,1002)
            return [equal,foreign,unmarked]
        result=self.capture(produce)
        self.assertTrue(result.evidence_complete);self.assertEqual(result.updates,())
        result=self.capture(lambda:[self.port.record(event,1001),event])
        self.assertEqual(len(result.updates),1)
        self.assertIs(result.updates[0].epoch,self.epoch);self.assertIs(result.updates[0].event,event)
        self.assertEqual(result.messages,(event,event))

    def test_account_store_token_phase_and_logout_changes_invalidate_evidence(self):
        mutations=(lambda:setattr(self.session,'account',SimpleNamespace(uid=1001,account_id=2,store=self.session.account.store)),
            lambda:setattr(self.session.account,'store',SimpleNamespace(uid=1001)),
            lambda:setattr(self.session,'shop_session_id','replacement'),
            lambda:setattr(self.session,'phase','dungeon_loading'),
            lambda:setattr(self.session,'released',True))
        for mutate in mutations:
            account=self.session.account;store=account.store
            self.session.shop_session_id='controlled-test-token';self.session.phase='town_ready';self.session.released=False
            event=self.event()
            def produce():
                self.port.record(event,1001);mutate();return [event]
            result=self.capture(produce)
            self.assertEqual(result.messages,(event,));self.assertFalse(result.evidence_complete);self.assertEqual(result.updates,())
            self.session.account=account;account.store=store

    def test_failed_producer_nested_scope_and_later_mailbox_do_not_leak(self):
        event=self.event()
        def fail():
            self.port.record(event,1001);raise RuntimeError('transaction failed')
        with self.assertRaises(RuntimeError):self.capture(fail)
        self.assertEqual(self.capture(lambda:[event]).updates,())
        def nested():
            child=self.capture(lambda:[self.port.record(event,1001)])
            self.assertEqual(len(child.updates),1)
            return [event]
        self.assertEqual(self.capture(nested).updates,())
        self.port.record(event,1001)
        self.assertEqual(self.capture(lambda:[event]).updates,())

    def test_count_byte_and_malformed_bounds_preserve_business_replies(self):
        event=self.event()
        def many():
            for _ in range(self.port.MAX_UPDATES+1):self.port.record(event,1001)
            return [event]
        for producer in(many,
                lambda:[self.port.record(Event(0x201,kind=0x123,payload=bytes(self.port.MAX_BYTES+1)),1001)],
                lambda:[self.port.record(event,True)]):
            result=self.capture(producer)
            self.assertFalse(result.evidence_complete);self.assertTrue(result.messages);self.assertEqual(result.updates,())

    def test_two_concurrent_workers_keep_context_and_epoch_identity(self):
        barrier=threading.Barrier(2)
        def work(owner):
            epoch=self.delivery.ActorEpoch(owner,2,5,owner)
            session=SimpleNamespace(account=SimpleNamespace(uid=owner,account_id=2,store=SimpleNamespace(uid=owner)),
                shop_session_id=str(owner),role='game',phase='town_ready',released=False)
            event=self.event()
            def producer():
                self.port.record(event,owner);barrier.wait(timeout=5);return [event]
            result=self.port.capture(epoch,session,producer)
            return result,epoch,event
        with ThreadPoolExecutor(max_workers=2)as pool:results=list(pool.map(work,(1001,1002)))
        for result,epoch,event in results:
            self.assertTrue(result.evidence_complete);self.assertEqual(len(result.updates),1)
            self.assertIs(result.updates[0].epoch,epoch);self.assertIs(result.updates[0].event,event)
            self.assertEqual(result.updates[0].owner,epoch.owner_uid)

    def test_extraction_receipt_binds_original_producer_pair_and_prefix(self):
        event=Event(0x201,kind=0x6cf,payload=struct.pack('>iiBI',0,900405,6,0))
        result=self.capture(lambda:[self.port.record(event,1001,removed_extra=(900405,6))])
        self.assertTrue(result.evidence_complete);self.assertEqual(result.updates[0].removed_extra,(900405,6))
        for pair in(None,(900405,3),(True,6),[900405,6]):
            result=self.capture(lambda:[self.port.record(event,1001,removed_extra=pair)])
            self.assertEqual(result.messages,(event,));self.assertFalse(result.evidence_complete);self.assertEqual(result.updates,())

    def test_all_writer_deltas_preserve_each_channel_parent_exactly(self):
        binding=json.loads((A/'native-skill-production-writer-binding.json').read_bytes())
        self.assertEqual(len(binding['rows']),22)
        for dependency in binding['dependencies']:
            self.assertFalse(dependency['runtime_delta'])
            self.assertEqual(hashlib.sha256((A/dependency['path']).read_bytes()).hexdigest(),dependency['sha256'])
        for row in binding['rows']:
            raw=(A/row['candidate_path']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),row['candidate_sha256'])
            newline=b'\r\n'if b'\r\n'in raw else b'\n'
            for before,after in reversed(row['changes']):
                old=before.encode().replace(b'\n',newline);new=after.encode().replace(b'\n',newline)
                self.assertEqual(raw.count(new),1);raw=raw.replace(new,old)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),row['source_before_sha256'])
        per_channel={r['channel']:r for r in binding['rows']if r['path']=='domain/local_session.py'}
        self.assertNotEqual(per_channel['online']['parent_sha256'],per_channel['local']['parent_sha256'])


if __name__=='__main__':unittest.main()
