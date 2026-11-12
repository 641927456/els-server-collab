"""Exhaustive discrete choices and numeric boundaries against native code."""
from pathlib import Path
import ast,hashlib,itertools,json,os,struct,sys,time,traceback
R=Path('G:/els');W=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path[:0]=[str(W.parent/'transport-routing-variants-v1/full-source-v1'),str(R/'tools/pylibs'),str(R/'tools'),str(R)]
os.environ['ELS_RUNTIME_IMAGE']=str(R/'analysis/client-6c6b5180/x2-runtime.bin')
import els_server.protocol
els_server.protocol.__path__.insert(0,str(W/'candidate/els_server/protocol'))
from els_server.protocol import pet_battle_messages as wire
from role_native_replay import Replay,IMAGE_SHA
helper=R/'tools/verify_pet_support_offline.py'
node=next(n for n in ast.parse(helper.read_text('utf8')).body if isinstance(n,ast.FunctionDef)and n.name=='stream')
exec(compile(ast.Module(body=[node],type_ignores=[]),str(helper)+' stream only','exec'))
report=dict(ok=False,image_sha256=IMAGE_SHA,source_sha256=hashlib.sha256(Path(wire.__file__).read_bytes()).hexdigest(),
    native_Game=False,natural_GUI=False,production_database_access=False,checks=[],native_oracle=True)
try:
    r=Replay()
    def writer():
        s,b=stream(r,bytes(512));start=int.from_bytes(r.read(b+8,8),'little');r.write(b+16,struct.pack('<Q',start));return s,b
    def output(b):
        first,last=struct.unpack('<QQ',r.read(b+8,16));return r.read(first,last-first)
    def vector(raw,stride):
        assert len(raw)%stride==0
        data=r.alloc(len(raw));r.write(data,raw);v=r.alloc(24);r.write(v,struct.pack('<QQQ',data,data+len(raw),data+len(raw)));return v
    count=0
    for choices in itertools.product((-1,0,1,2,3),repeat=3):
        s,b=writer();mode=vector(bytes((13,0,0)),3)
        assert r.call(0x2bde630,s,mode)&255==1
        hint=-2147483648 if count%2 else 2147483647
        assert r.call(0x3b6dbd0,s,hint&0xffffffff)&255==1
        ids=(0,2**63-1,2**64-1)
        related=vector(b''.join(struct.pack('<QB7x',uid,255 if choice==-1 else choice)for uid,choice in zip(ids,choices)),16)
        assert r.call(0x2bde710,s,related)&255==1
        assert wire.selection(output(b))==(hint,tuple(zip(ids,choices)))
        count+=1
    report['checks'].append(dict(original342_serializers=['2BDE630','2BDE710'],all_growth_combinations=count,
        opaque_hint_i32_boundaries=True,UID_u64_boundaries=True,zero_UID_is_format_only=True))
    count=0
    action_sets=list(itertools.product(range(6),repeat=3))+[(-2147483648,2147483647,0)]
    for actions in action_sets:
        targets=(0,2**63-1,2**64-1);rows=tuple(zip(actions,targets));s,b=writer()
        value=vector(b''.join(struct.pack('<iQ',a,u)for a,u in rows),12)
        assert r.call(0xdb8560,s,value)&255==1
        pet=2**64-1 if count%2 else 0
        assert r.call(0x3b6dda0,s,pet)&255==1
        raw=output(b);assert wire.actions(raw)==(rows,pet)
        count+=1
    for length in range(48):
        try:wire.actions(bytes(length))
        except ValueError:pass
        else:raise AssertionError(('Truncated action body accepted',length))
    for bad in (0,1,2,4,2**32-1):
        try:wire.actions(struct.pack('>I',bad)+raw[4:])
        except ValueError:pass
        else:raise AssertionError(('Wrong action count accepted',bad))
    report['checks'].append(dict(original_A6C_serializer='DB8560',all_action_combinations=216,
        extra_numeric_boundary_case=True,cases=count,rejects_all_truncated_lengths=True,rejects_non_three_count=True,
        business_action_legality_not_claimed=True))
    rows=[(dict(uid=9001,unit=1,name='甲',step=2),-1,100,0),
          (dict(uid=9002,unit=2,name='乙🙂',step=2),0,57,2),
          (dict(uid=9003,unit=3,name='C',step=2),3,0,1)]
    for values in ([],rows):
        raw=wire.pets(values);s,b=stream(r,raw);v=r.alloc(24);r.call(0xdc6880,s,v)
        first,last,cap=struct.unpack('<QQQ',r.read(v,24));assert last-first==len(values)*0x107
        assert int.from_bytes(r.read(b+32,4),'little')==len(raw)
        for i,(pet,*extra)in enumerate(values):
            assert int.from_bytes(r.read(first+i*0x107,8),'little')==pet['uid']
            assert struct.unpack('<iii',r.read(first+i*0x107+0xfb,12))==tuple(extra)
    report['checks'].append(dict(original_DC6880_reader=True,empty_and_three_pet_vectors=True,
        exact_UID_and_three_i32_fields=True,HP_and_enchant_are_explicit_layout_fixtures=True))
    assert wire.action_ack(0).kind==0xa6d and wire.action_ack(-1).payload==struct.pack('>i',-1)
    report['ok']=True
except BaseException:report['error']=traceback.format_exc()
p=W/('codec-native-'+str(time.time_ns())+'.json');p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(report|dict(evidence=str(p)),ensure_ascii=False))
raise SystemExit(not report['ok'])
