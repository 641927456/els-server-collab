"""Original complete slot/FullUser reader with the new pet-state projection."""
from pathlib import Path
import hashlib,importlib.util,json,os,struct,sys,time,traceback
R=Path('G:/els');W=Path(__file__).resolve().parent
B=W.parent/'transport-routing-variants-v1/full-source-v1'
sys.dont_write_bytecode=True;sys.path[:0]=[str(B),str(R/'tools'),str(R/'tools/pylibs'),str(R)]
os.environ['ELS_RUNTIME_IMAGE']=str(R/'analysis/client-6c6b5180/x2-runtime.bin')
import els_server.protocol
els_server.protocol.__path__.insert(0,str(W/'candidate/els_server/protocol'))
from els_server.protocol import dungeon_messages as wire
from els_server.storage.characters import DEFAULT_CHARACTER
from els_server.domain.skill_state import DEFAULT_SLOTS
from role_native_replay import Replay,IMAGE_SHA
from verify_pet_support_offline import stream
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RAX

report=dict(ok=False,image_sha256=IMAGE_SHA,native_Game=False,natural_GUI=False,
    production_database_access=False,layout_fixture=True,checks=[])
try:
    spec=importlib.util.spec_from_file_location('pet_member_baseline',B/'els_server/protocol/dungeon_messages.py')
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    character=dict(DEFAULT_CHARACTER,account_id=2,name='NativePetOwner')
    normal=old.member(DEFAULT_SLOTS,character,[],account_id=2,peer_port=21100)
    assert wire.member(DEFAULT_SLOTS,character,[],account_id=2,peer_port=21100)==normal
    report['checks'].append(dict(ordinary_member_without_pet_projection_byte_identical=True,bytes=len(normal)))
    pets=[(dict(uid=9001,unit=1,name='原生甲',step=2),-1,100,0),
          (dict(uid=9002,unit=2,name='原生乙🙂',step=2),0,57,2),
          (dict(uid=9003,unit=3,name='NativeC',step=2),3,0,1)]
    full=wire.member(DEFAULT_SLOTS,character,[],account_id=2,peer_port=21100,pet_fight=pets)
    raw=struct.pack('>I',1)+bytes((0,4,1,1,0,0))+struct.pack('>iI',0,1)+full+bytes(8)
    r=Replay();r.uc.hook_add(UC_HOOK_CODE,lambda uc,a,n,u:r.finish_shim(uc.reg_read(UC_X86_REG_RAX)),
        begin=r.base+0x3ae43c0,end=r.base+0x3ae43c0)
    reader,buffer=stream(r,raw);slots=r.alloc(24);r.call(0xdb7cf0,reader,slots)
    first,last,cap=struct.unpack('<QQQ',r.read(slots,24));assert last-first==0x3e
    member,end,cap=struct.unpack('<QQQ',r.read(first+0xa,24));assert end-member==0x6b0
    assert int.from_bytes(r.read(buffer+32,4),'little')==len(raw)
    assert int.from_bytes(r.read(member+0xe1,8),'little')==character['uid']
    assert int.from_bytes(r.read(member+0x137,2),'little')==21100
    begin,end,cap=struct.unpack('<QQQ',r.read(member+0x5ec,24));assert end-begin==3*0x107
    for i,(pet,*values)in enumerate(pets):
        p=begin+i*0x107;assert int.from_bytes(r.read(p,8),'little')==pet['uid']
        assert struct.unpack('<iii',r.read(p+0xfb,12))==tuple(values)
    assert r.read(member+0x604,8)==bytes(8)
    report['checks'].append(dict(original_DB7CF0_D9DDB0_D9D2F0_full_read=True,slot_count=1,member_count=1,
        pet_count=3,all_pet_UID_and_ability_HP_enchant_fields_match=True,account_owner_and_port_retained=True,
        ordinary_mount_field_unchanged=True,bytes=len(raw),original_code_unmodified=True,
        external_windows_stack_probe_stubbed=True))
    report.update(ok=True,sources={p.relative_to(W/'candidate').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for p in(W/'candidate').rglob('*.py')})
except BaseException:report['error']=traceback.format_exc()
p=W/('native-member-'+str(time.time_ns())+'.json');p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(report|dict(evidence=str(p)),ensure_ascii=False))
raise SystemExit(not report['ok'])
