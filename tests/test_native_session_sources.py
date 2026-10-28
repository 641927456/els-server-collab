"""Lifecycle/failed-write controls; real App and native wire proofs are separate."""
from pathlib import Path
from types import ModuleType,SimpleNamespace
from unittest.mock import patch
from contextlib import ExitStack
import importlib,struct,sys,threading,unittest
from els_server.protocol.protocol_codec import Event

U32=lambda n:struct.pack('>I',n)
def records(values):return U32(len(values))+b''.join(struct.pack('>iBiB',sid,rank,0,0)for sid,rank in values)
def preset(forces):
    return records(((0,0),)*22)+U32(0)+U32(3)+b''.join(struct.pack('>iBB',s,r,0)for s,r in forces[:3])+U32(8)+b''.join(struct.pack('>iBB',s,r,0)for s,r in forces[3:])
def copy_event(*,uid,kind,forces):
    field=records(((0,0),)*22)+bytes(4)+records(((25410,4),))+bytes(8)+b'\1\1'+preset(forces)+records(((25410,4),))+b'\0'
    fields=(('prefix',bytes(9)+struct.pack('>Q',uid)),('0x14e',field))
    return None,fields
def initial(*,forces):
    body=struct.pack('>QI',1001,1)+b'\0'+preset(forces)+records(((25410,4),(25030,1)))+bytes(17)+b'\1\1'+U32(0)
    return Event(0x201,kind=0x55b,payload=body)


class SessionSourcesTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        import els_server.domain as domain
        source=Path(__file__).resolve().parents[1]/'references/native-skill-source-runtime-20261028-v1/common/els_server/domain'
        self.stack.enter_context(patch.object(domain,'__path__',[str(source),*domain.__path__]))
        self.stack.enter_context(patch.dict(sys.modules))
        missing=object()
        for name in('native_skill_delivery_sources','native_skill_production','native_copy_production',
                     'native_attribute_readiness','native_attribute_delivery','native_session_sources'):
            old=getattr(domain,name,missing)
            def restore(name=name,old=old):
                if old is missing:
                    if hasattr(domain,name):delattr(domain,name)
                else:setattr(domain,name,old)
            self.stack.callback(restore)
            if hasattr(domain,name):delattr(domain,name)
            sys.modules.pop('els_server.domain.'+name,None)
        class LocalSession:
            def handle(self,event,request_sequence=None):raise AssertionError('Explicit unit seam required')
        self.kind=LocalSession
        local=ModuleType('els_server.domain.local_session');local.LocalSession=LocalSession
        self.stack.enter_context(patch.dict(sys.modules,{local.__name__:local}))
        self.subject=self.kind.__new__(self.kind)
        self.subject.account=SimpleNamespace(uid=1001,account_id=2,store=SimpleNamespace(uid=1001))
        self.subject.shop_session_id='explicit-unit-token';self.subject.role='game';self.subject.released=False
        self.subject.phase='channels_ready';self.subject.client_build='dx11_260923';self.subject.enter_town=True
        self.native=importlib.import_module('els_server.domain.native_session_sources')
        data=ModuleType('els_server.game_data');data.client_data=lambda:SimpleNamespace(unit=lambda cls:{'unitType':5})
        self.stack.enter_context(patch.dict(sys.modules,{data.__name__:data}))
        def handle(session,event,request_sequence=None):
            if event.kind==0x28:
                _,parts=copy_event(uid=session.account.uid,kind=0x2a,forces=((0,0),)*11)
                fields=(parts[0],('0x11',bytes(4)),('0x15',struct.pack('>H',164)),parts[1])
                self.native.copies.capture_fields(fields)
                session.phase='player_initialized'
                return [Event(0x201,kind=0x2a,payload=bytes(4)+b''.join(value for key,value in fields)),initial(forces=((0,0),)*11)]
            if event.kind==0x6e9:
                session.phase='skill_ui_ready';return [Event(0x201,kind=0x6ea,payload=b'explicit-unit-layout')]
            return []
        self.stack.enter_context(patch.object(self.kind,'handle',handle))
        self.state=self.native.attach(self.subject)

    def call(self,kind,*,after=None):
        function=self.subject.handle;args=(Event(0x202,kind=kind,payload=b''),);kwargs={'request_sequence':7}
        saved=[]
        def invoke():
            value=function(*args,**kwargs)
            if after is not None:after(value)
            saved.append(value);return value
        result=self.native.capture(function,args,kwargs,invoke)
        self.assertIs(result,saved[0])
        return result

    def select(self):
        result=self.call(0x28);self.assertTrue(self.state.sent(result));return self.state.cursor.epoch

    def test_only_complete_original_write_advances_and_failed_transport_closes(self):
        result=self.call(0x28);epoch=self.state.cursor.epoch
        self.assertIsNotNone(epoch);self.assertFalse(self.state.cursor._copied)
        self.state.close()
        self.assertFalse(self.state.sent(result));self.assertIsNone(self.state.cursor.epoch)

    def test_original_UI_reply_identity_then_reselection_and_empty_periodic(self):
        epoch=self.select();reply=self.call(0x6e9)
        self.assertFalse(self.state.cursor._ui_ready)
        self.assertTrue(self.state.sent(reply));self.assertTrue(self.state.cursor._ui_ready)
        revision=self.state.cursor.revision
        self.assertTrue(self.state.sent(self.call(0x7d0)));self.assertEqual(self.state.cursor.revision,revision)
        next_copy=self.call(0x28)
        self.assertIsNot(self.state.cursor.epoch,epoch);self.assertFalse(self.state.cursor._ui_ready)
        self.assertFalse(self.state.cursor._copied);self.assertTrue(self.state.sent(next_copy))

    def test_equal_looking_replaced_store_or_reply_cannot_attest_delivery(self):
        self.select();reply=self.call(0x6e9)
        clone=[Event(e.event_id,kind=e.kind,payload=e.payload)for e in reply]
        self.assertFalse(self.state.sent(clone));self.assertIsNone(self.state.cursor.epoch)
        self.select();reply=self.call(0x6e9)
        self.subject.account.store=SimpleNamespace(uid=1001)
        self.assertFalse(self.state.sent(reply));self.assertIsNone(self.state.cursor.epoch)

    def test_after_reply_updates_are_captured_without_reinvoking_business(self):
        self.select();self.state.sent(self.call(0x6e9));self.subject.phase='town_ready'
        def after(messages):
            event=Event(0x201,kind=0x123,payload=struct.pack('>5i',0,0,25030,-1,0))
            self.native.skills.record(event,1001);messages.append(event)
        result=self.call(0x7d0,after=after)
        self.assertEqual(len(self.state._pending.updates),1)
        self.assertIs(self.state._pending.updates[0].event,result[0]);self.assertTrue(self.state.sent(result))

    def test_metadata_failure_preserves_original_result_and_business_failure_is_not_retried(self):
        self.select();calls=[];result=[]
        def invoke():calls.append(1);return result
        with patch.object(self.native.copies,'capture',side_effect=ValueError('metadata-only failure')):
            self.assertIs(self.state.capture(self.subject.handle,(),{},invoke),result)
        self.assertEqual(len(calls),1);self.assertIsNone(self.state.cursor.epoch)
        def broken():calls.append(2);raise RuntimeError('original business failure')
        with self.assertRaisesRegex(RuntimeError,'original business failure'):
            self.state.capture(self.subject.handle,(),{},broken)
        self.assertEqual(calls,[1,2])

    def test_close_during_worker_cannot_revive_pending_epoch(self):
        self.select();entered=threading.Event();resume=threading.Event();answers=[]
        def invoke():entered.set();self.assertTrue(resume.wait(3));return []
        worker=threading.Thread(target=lambda:answers.append(self.state.capture(self.subject.handle,(),{},invoke)))
        worker.start();self.assertTrue(entered.wait(3));self.state.close();resume.set();worker.join(3)
        self.assertFalse(worker.is_alive());self.assertEqual(answers,[[]]);self.assertIsNone(self.state.cursor.epoch)
        self.assertIsNone(self.state._pending)


if __name__=='__main__':unittest.main()
