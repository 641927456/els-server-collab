"""Original full2F decoder and original partner copy for saved relationships."""
from pathlib import Path
import hashlib,json,struct,sys,time,traceback
R=Path('G:/els');W=Path(__file__).resolve().parent;B=W/'full-source-v4'
sys.dont_write_bytecode=True;sys.path[:0]=[str(B),str(R/'tools'),str(R/'tools/pylibs'),str(R)]
from els_server.protocol.local_messages import optional_player_initializations
from els_server.protocol.friend_messages import restore
from role_native_replay import Replay,IMAGE_SHA
from verify_pet_support_offline import stream
report=dict(ok=False,image_sha256=IMAGE_SHA,live_process_access=False,natural_GUI=False,cases=[])
try:
    r=Replay()
    for row in(None,dict(uid=1002,level=15,name='WirePupil',online=True,unlock_at='2026-11-08 06:00:00',rank=0,is_student=True,unit_class=1),
               dict(uid=1001,level=99,name='NativeTutor',online=False,unlock_at='2026-11-08 06:00:00',rank=2,is_student=False,unit_class=100)):
        partners=()if row is None else(row,)
        base=next(e for e in optional_player_initializations(True)if e.kind==0x2f)
        friends=[dict(uid=2001,name='NativeFriend',group=1,status=0,online=1,unit_type=1,unit_class=100,level=99,rank=0,guild_name='',channel=1,map=20000,context_flag=1)]
        raw=restore(base,dict(friends=friends,groups={1:'Friends'},pending=[]),mentor_partners=partners).payload
        s,b=stream(r,raw);dto=r.alloc(0x164);r.call(0x13f7550,dto)
        assert r.call(0xda37c0,s,dto)&255==1 and int.from_bytes(r.read(b+32,4),'little')==len(raw)
        start,end=struct.unpack('<QQ',r.read(dto+0x2f,16));assert end-start==len(partners)*0x71
        assert struct.unpack('<Q',r.read(dto+0x97,8))[0]==1
        assert struct.unpack('<Q',r.read(dto+0xa7,8))[0]==1
        if row is not None:
            manager=r.alloc(0x200);r.call(0x21c1230,manager+0x78);r.call(0x21b2980,manager,start)
            assert struct.unpack('<Q',r.read(manager+0x78,8))[0]==row['uid']
            assert struct.unpack('<I',r.read(manager+0x80,4))[0]==row['level']
            assert bool(r.read(manager+0xa8,1)[0])==row['online']
            assert bool(r.read(manager+0xd0,1)[0])==row['is_student']
            assert struct.unpack('<i',r.read(manager+0xd4,4))[0]==row['unit_class']
        report['cases'].append(dict(partner=None if row is None else row['uid'],bytes=len(raw),original_full2F_DA37C0=True,original_partner_copy_21B2980=row is not None,existing_friend_and_group_both_restored=True))
    report['ok']=True
except BaseException:report['error']=traceback.format_exc()
report['binding_sha256']=hashlib.sha256((W/'candidate-source-binding-v4.json').read_bytes()).hexdigest()
out=W/('mentor-initialization-native-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,indent=2)+'\n','utf8')
print(json.dumps(report|dict(evidence=str(out))));raise SystemExit(not report['ok'])
