"""Challenge input grammar, frozen invitation identity and corruption boundaries."""
from pathlib import Path
import hashlib,json,struct,sys,time,unittest
W=Path(__file__).resolve().parent;R=Path('G:/els')
B=R/'releases/local/unified-server-566743b0f3babdfb-749ffeb2e0ca'
sys.dont_write_bytecode=True
sys.path[:0]=[str(B),str(R/'analysis/pr771-racing-local-20261103-v1/test-libs')]
import els_server,els_server.protocol
els_server.protocol.__path__.insert(0,str(W/'candidate/els_server/protocol'))
from hypothesis import given,settings,strategies as st
from els_server.protocol import duel_messages as wire
from els_server.protocol.local_messages import wstring

uids=st.integers(min_value=1,max_value=2**63-1)
maps=st.sets(st.integers(min_value=-32768,max_value=32767),max_size=12)
hint=st.integers(min_value=0,max_value=2**32-1)
names=st.sampled_from(('OwnDuel','切磋甲','Éclair','对决乙'))
set_bytes=lambda values:struct.pack('>I',len(values))+b''.join(struct.pack('>h',v)for v in sorted(values))

class ChallengeProperties(unittest.TestCase):
    @settings(max_examples=70,deadline=None,database=None,derandomize=True)
    @given(uids,uids,hint,hint,names,maps,st.integers(0,255),st.integers(-2**31,2**31-1))
    def test_original_invitation_fields_and_exact_boundary(self,own,target,first,second,name,excluded,flag,final):
        raw=struct.pack('>QIQI',own,first,target,second)+wstring(name)+set_bytes(excluded)+struct.pack('>Bi',flag,final)
        parsed=wire.invitation_request(raw)
        self.assertEqual(parsed,dict(sender=own,target=target,name=name,first_hint=first,second_hint=second,
            excluded=frozenset(excluded),flag=flag,final_hint=final))
        invited=wire.invited(own,target,first,second,name,b'fixture-body',excluded,flag)
        self.assertEqual(invited.payload[:24],struct.pack('>QIQI',own,first,target,second))
        self.assertEqual(invited.payload[24:],wstring(name)+b'fixture-body'+set_bytes(excluded)+bytes((flag,)))
        for corrupt in(raw[:-1],raw+b'\0',raw[:24]+struct.pack('>I',len(raw)*2)+raw[28:]):
            with self.assertRaises(ValueError):wire.invitation_request(corrupt)

    @settings(max_examples=80,deadline=None,database=None,derandomize=True)
    @given(uids,uids,st.binary(min_size=20,max_size=300),maps,st.sampled_from((0,1,2)),st.integers(-2**31,2**31-1))
    def test_answer_is_bound_to_server_snapshot_and_both_invitation_UIDs(self,own,target,body,excluded,decision,final):
        raw=struct.pack('>QQi',own,target,decision)+body+set_bytes(excluded)+struct.pack('>i',final)
        parsed=wire.answer_request(raw,inviter=own,recipient=target,full_user=body)
        self.assertEqual(parsed,dict(inviter=own,recipient=target,decision=decision,excluded=frozenset(excluded),final_hint=final))
        changed=raw[:20]+bytes((body[0]^1,))+raw[21:]
        for corrupt in(changed,raw+b'\0',raw[:-1],struct.pack('>QQi',own,target,3)+raw[20:]):
            with self.assertRaises(ValueError):wire.answer_request(corrupt,inviter=own,recipient=target,full_user=body)
        with self.assertRaises(ValueError):wire.answer_request(raw,inviter=own^1,recipient=target,full_user=body)
        with self.assertRaises(ValueError):wire.answer_request(raw,inviter=own,recipient=target^1,full_user=body)

    @settings(max_examples=60,deadline=None,database=None,derandomize=True)
    @given(st.binary(max_size=1000))
    def test_arbitrary_payloads_have_only_explicit_parse_failure(self,raw):
        try:wire.invitation_request(raw)
        except ValueError:pass
        try:wire.answer_request(raw,inviter=1,recipient=2,full_user=bytes(20))
        except ValueError:pass

    def test_native_sorted_map_set_and_cancellation(self):
        raw=struct.pack('>QIQI',1,0,2,0)+wstring('OwnDuel')
        for values in((1,1),(2,1)):
            corrupt=raw+struct.pack('>IhhBi',2,*values,0,0)
            with self.assertRaises(ValueError):wire.invitation_request(corrupt)
        self.assertTrue(wire.cancel_request(b'\1'));self.assertFalse(wire.cancel_request(b'\0'))
        for value in(b'',b'\2',b'\1\0'):
            with self.assertRaises(ValueError):wire.cancel_request(value)

suite=unittest.defaultTestLoader.loadTestsFromTestCase(ChallengeProperties)
result=unittest.TextTestRunner(verbosity=1).run(suite)
report=dict(ok=result.wasSuccessful(),tests=result.testsRun,generated_examples=210,
    source_sha256=hashlib.sha256((W/'candidate/els_server/protocol/duel_messages.py').read_bytes()).hexdigest(),
    business_dispatch=False,installed=False,production_data_access=False)
(W/('wire-properties-'+str(time.time_ns())+'.json')).write_bytes((json.dumps(report,indent=2)+'\n').encode('utf8'))
print(json.dumps(report));raise SystemExit(not result.wasSuccessful())
