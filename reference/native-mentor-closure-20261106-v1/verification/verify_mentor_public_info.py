"""Qualify mentor public records against the original reader, writer and UI copy."""
from pathlib import Path
import hashlib,json,os,struct,sys,time,traceback
R=Path('G:/els');W=Path(__file__).resolve().parent
B=R/'releases/local/unified-server-566743b0f3babdfb-749ffeb2e0ca'
sys.dont_write_bytecode=True
sys.path[:0]=[str(B),str(R/'tools'),str(R/'tools/pylibs'),str(R)]
os.environ['ELS_RUNTIME_IMAGE']=str(R/'analysis/client-6c6b5180/x2-runtime.bin')
import els_server,els_server.protocol
els_server.protocol.__path__.insert(0,str(W/'candidate/els_server/protocol'))
from els_server.protocol import mentor_messages as wire
from role_native_replay import Replay,IMAGE_SHA
from verify_pet_support_offline import stream
from unicorn.x86_const import UC_X86_REG_RIP

def text(r,address):
    length,capacity=struct.unpack('<QQ',r.read(address+16,16))
    assert length<256
    data=address if capacity<=7 else struct.unpack('<Q',r.read(address,8))[0]
    return r.read(data,length*2).decode('utf-16le')

report=dict(ok=False,image_sha256=IMAGE_SHA,source_type='Original image/default symbols only',
    native_reader='DB5210',native_writer='DB5150',native_UI_copy='21B2980',cases=[],
    live_process_access=False,production_database_access=False,natural_GUI=False)
try:
    cases=[dict(uid=uid,level=level,name=name,online=online,unlock_at=until,rank=rank,
        is_student=student,unit_class=career) for uid,level,name,online,until,rank,student,career in [
        (1001,99,'师傅A',True,'2026-11-08 12:34:56',7,False,1064),
        (1002,1,'Student🙂',True,'2026-11-08 12:34:56',0,True,0),
        (1003,99,'毕业角色',False,'',8,True,1211),
        (2**64-1,0,'',False,'',0,False,0),
        (1004,35,'SecondJob',False,'1970-01-01 00:00:00',65535,False,2**31-1),
    ]]
    r=Replay()
    for row in cases:
        raw=wire.public_info(row)
        incoming,buffer=stream(r,raw);dto=r.alloc(0x51)
        r.call(0xdf6040,dto)
        assert r.call(0xdb5210,incoming,dto)&255==1
        assert struct.unpack('<I',r.read(buffer+32,4))[0]==len(raw)
        outgoing,encoded=stream(r,b'')
        assert r.call(0xdb5150,outgoing,dto)&255==1
        begin,end,capacity=struct.unpack('<QQQ',r.read(encoded+8,24))
        assert r.read(begin,end-begin)==raw
        manager=r.alloc(0x200)
        # 21C1230 resets an already constructed UI record; std::wstring's
        # empty SSO capacity is7, not an unconstructed zero-filled object.
        empty=r.alloc(0x51);r.call(0xdf6040,empty)
        r.write(manager+0x88,r.read(empty+9,32))
        r.write(manager+0xb0,r.read(empty+0x2a,32))
        r.call(0x21b2980,manager,dto)
        assert struct.unpack('<Q',r.read(manager+0x78,8))[0]==row['uid']
        assert struct.unpack('<i',r.read(manager+0x80,4))[0]==row['level']
        assert text(r,manager+0x88)==row['name'], dict(expected=row['name'],actual=text(r,manager+0x88),
            native_DTO=text(r,dto+9),UI_raw=r.read(manager+0x88,32).hex())
        assert r.read(manager+0xa8,1)==bytes((row['online'],))
        assert text(r,manager+0xb0)==row['unlock_at']
        assert r.read(manager+0xd0,1)==bytes((row['is_student'],))
        assert struct.unpack('<H',r.read(manager+0xd2,2))[0]==row['rank']
        assert struct.unpack('<i',r.read(manager+0xd4,4))[0]==row['unit_class']
        report['cases'].append(dict(uid=row['uid'],wire_bytes=len(raw),byte_exact=True,original_UI_fields_match=True))
    dto=r.alloc(0x51);r.call(0xdf6040,dto)
    outgoing,encoded=stream(r,b'');assert r.call(0xdb5150,outgoing,dto)&255==1
    begin,end,capacity=struct.unpack('<QQQ',r.read(encoded+8,24))
    assert r.read(begin,end-begin)==wire.EMPTY_ANSWER_INFO
    report.update(ok=True,original_default_answer_info_bytes=end-begin,source_sha256=hashlib.sha256(Path(wire.__file__).read_bytes()).hexdigest())
except BaseException:
    report['error']=traceback.format_exc()
    if 'r'in locals():report['native_pc']=hex(r.uc.reg_read(UC_X86_REG_RIP)-r.base)
path=W/('public-info-native-'+str(time.time_ns())+'.json')
path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(report|dict(evidence=str(path)),ensure_ascii=False))
raise SystemExit(not report['ok'])
