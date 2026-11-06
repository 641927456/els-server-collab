"""Exercise the real session dispatcher using one owned isolated save."""
import gc,json,sqlite3,struct,sys,tempfile
from contextlib import closing
from pathlib import Path
HERE=Path(__file__).parent;sys.path.insert(0,str(HERE/'runtime'))
from els_server.domain.local_session import LocalAccount,LocalSession
import els_server;assert Path(els_server.__file__).resolve().is_relative_to(Path(__file__).resolve().parent/'runtime'),els_server.__file__
from els_server.storage.local_state import LocalState
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.protocol.local_messages import wstring
from els_server.protocol.activity_2026_entries import CodeEntry,notice,read
from els_server.domain.quick_start_flow import synchronize

tmp=tempfile.TemporaryDirectory(dir=HERE,prefix='owned-session-');path=Path(tmp.name)/'game.sqlite3'
try:
    root=LocalAccount(LocalState(path));root.enable_characters()
    s=LocalSession(root,enter_town=True,enter_dungeon=True,client_build='dx11_260923',
        npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True)
    s.role='game';s.phase='characters_ready'
    initial=synchronize(s,[notice({518:CodeEntry(True,1,2)})])
    entries=read(next(e.payload for e in initial if e.kind==0x4b9))
    assert 518 in entries and entries[578].parameters==(1,)
    create=Event(0x202,performers=(0,),kind=0x489,payload=wstring('SessionQuick')+struct.pack('>iiBBIii',1,1,0,0,1,578,0))
    response=s.handle(create,1)
    assert next(e for e in response if e.kind==0x25).payload[:4]==bytes(4)
    uid=root.characters.list()[-1]['uid']
    assert struct.unpack_from('>Q',next(e.payload for e in response if e.kind==0xc55))[0]==uid
    s.account=root.for_character(uid);s.phase='town_ready';s.active_map=s.pending_map=20000
    from els_server.domain.quest_flow import store,initialization
    q=store(s)
    assert [r['id']for r in q.snapshot()['active']]==[169600]
    from els_server.domain.first_story_entry import pending_tutorial
    assert not pending_tutorial(s)
    assert initialization(s).kind==0x2b
    from els_server.domain.region_quests import account_dungeon_allowed
    assert account_dungeon_allowed(s.account,30000)
    assert not account_dungeon_allowed(s.account,30102)
    denied=s.handle(Event(0x202,performers=(0,),kind=0xc56,payload=struct.pack('>i',100)),2)
    assert struct.unpack_from('>i',next(e.payload for e in denied if e.kind==0xc57))[0]!=0
    q.record('owned-session-kill',dict(kind='kill',dungeon=30000,level=1,npc=5),b'controlled-native-observer-input')
    reward=s.handle(Event(0x202,performers=(0,),kind=0xf4,payload=struct.pack('>iiI5B',169600,0,0,0,0,1,1,0)),3)
    assert struct.unpack_from('>i',next(e.payload for e in reward if e.kind==0xf5))[0]==0
    from els_server.domain.careers import PARENTS
    target=next(c for c,p in PARENTS.items()if p==1)
    changed=s.handle(Event(0x202,performers=(0,),kind=0xc56,payload=struct.pack('>i',target)),4)
    assert next(e for e in changed if e.kind==0xc57).payload[:4]==bytes(4)
    assert s.account.character()['unit_class']==target
    assert account_dungeon_allowed(s.account,30102)
    for event in initial+response+reward+changed:encode_event(event)
    report=dict(passed=True,original_creation_option=578,create_ack=True,account_enrollment_uid=uid,
        other_code_event_preserved=True,ordinary_tutorial_suppressed=True,quest_reward_dispatch=True,
        early_career_rejected=True,career_request_dispatch=True,event_dungeon_gate=True,
        layer='Real LocalSession dispatcher and owned SQLite; controlled observer input, no live GUI/network')
    (HERE/'session-proof.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report))
finally:
    gc.collect();tmp.cleanup()
