"""Same producer/Event identity, bounded memory and context/thread isolation."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import importlib.util,sys,threading,unittest
from pathlib import Path
from unittest.mock import patch
from tests.test_native_skill_delivery_sources import copy_event,notice
ROOT=Path(__file__).resolve().parents[1]
A=ROOT/'references/native-server-attributes-20261027-v1'


class CopyProductionTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        import els_server.domain as domain
        self.stack.enter_context(patch.object(domain,'__path__',[str(A/'els_server/domain'),*domain.__path__]))
        self.stack.enter_context(patch.dict(sys.modules))
        for name in('native_skill_delivery_sources','native_copy_production'):
            spec=importlib.util.spec_from_file_location('els_server.domain.'+name,A/'els_server/domain'/(name+'.py'))
            module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
            self.stack.enter_context(patch.object(domain,name,module,create=True))
        self.port=module

    def test_actual_producer_events_bind_only_the_exact_complete_emitted_prefix(self):
        source=((100100,5),)+((0,0),)*10
        for kind in(0x2a,0xd9):
            event,fields=copy_event(forces=source,kind=kind)
            def produce():
                self.assertIs(self.port.capture_fields(fields),fields)
                return [event]
            result=self.port.capture(produce)
            self.assertTrue(result.evidence_complete)
            self.assertEqual(len(result.copies),1)
            self.assertIs(result.messages[0],event);self.assertIs(result.copies[0].event,event)
            self.assertEqual(result.copies[0].preset.forces,source)

    def test_other_owner_later_fields_and_payload_substrings_cannot_attest_a_copy(self):
        event,fields=copy_event()
        foreign,_=copy_event(uid=1002)
        changed,_=copy_event(forces=((100100,5),)+((0,0),)*10)
        for different in(foreign,changed,notice(0xd9,b'unrelated-prefix'+event.payload)):
            result=self.port.capture(lambda:(self.port.capture_fields(fields),[different])[1])
            self.assertEqual(result.copies,())
        self.port.capture_fields(fields)  # Outside a producer has no retained state.
        self.assertEqual(self.port.capture(lambda:[event]).copies,())

    def test_count_and_byte_budget_drop_evidence_without_changing_business_replies(self):
        event,fields=copy_event()
        def many():
            for _ in range(self.port.MAX_COPIES+1):self.port.capture_fields(fields)
            return [event]
        result=self.port.capture(many)
        self.assertEqual(result.messages,(event,));self.assertFalse(result.evidence_complete);self.assertEqual(result.copies,())
        oversized=(('prefix',bytes(self.port.MAX_BYTES+1)),)
        result=self.port.capture(lambda:(self.port.capture_fields(oversized),[event])[1])
        self.assertFalse(result.evidence_complete);self.assertEqual(result.messages,(event,));self.assertEqual(result.copies,())
        result=self.port.capture(lambda:(self.port.capture_fields(list(fields)),[event])[1])
        self.assertFalse(result.evidence_complete);self.assertEqual(result.messages,(event,));self.assertEqual(result.copies,())

    def test_exception_and_nested_scopes_do_not_leak_source_records(self):
        event,fields=copy_event()
        def fail():
            self.port.capture_fields(fields);raise RuntimeError('owned producer failure')
        with self.assertRaises(RuntimeError):self.port.capture(fail)
        self.assertEqual(self.port.capture(lambda:[event]).copies,())
        def outer():
            inner=self.port.capture(lambda:(self.port.capture_fields(fields),[event])[1])
            self.assertEqual(len(inner.copies),1)
            return inner.messages
        self.assertEqual(self.port.capture(outer).copies,())

    def test_concurrent_workers_keep_owned_records_in_separate_contexts(self):
        barrier=threading.Barrier(2)
        def work(owner):
            event,fields=copy_event(uid=owner)
            def produce():
                self.port.capture_fields(fields);barrier.wait(3);return [event]
            return self.port.capture(produce)
        with ThreadPoolExecutor(max_workers=2)as pool:
            futures=[pool.submit(work,owner)for owner in(1001,1002)]
            results=[f.result(4)for f in futures]
        self.assertEqual([r.copies[0].owner for r in results],[1001,1002])


if __name__=='__main__':unittest.main()
