"""Writer-local character projections and original housing/guild member readers."""
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import hashlib,json,sqlite3,struct,sys,tempfile,time,traceback
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_full_unit_projection import W,Characters,state,UnitReplay,status,stream
from els_server.storage.game_schema import prepare
from els_server.storage.seal_quests import load_character,current_slots
from els_server.storage.career_shop import notifications
from els_server.storage.inventory_state import load_items
from els_server.storage import characters as characters_module
from els_server.protocol import character_messages,quest_messages,housing_population_messages,guild_agit_messages,local_messages,dungeon_messages
from els_server.domain.achievement_catalog import achievement


report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,
    original_reader_replay=True,completion_fixture=True,cases=[])
try:
    with tempfile.TemporaryDirectory(prefix='owned-achievement-transaction-unit-',dir=W)as folder:
        path=Path(folder)/'own.sqlite3';prepare(path);chars=Characters(path,1)
        uid=chars.create('AchTxnA',1,'owned-txn-create-A')['uid']
        with closing(sqlite3.connect(path))as db,db:
            db.execute('BEGIN IMMEDIATE')
            state.record(db,1,uid,[dict(achievement=19,condition=c['id'],value=1,complete=True)for c in achievement(19)['conditions']],
                'owned-txn-completion',int(time.time()))
            state.toggle_display(db,1,uid,19,'owned-txn-display')
        expected=dict(points=[10,0,0,0],watched=[19],state_flag=False)
        replay=UnitReplay();captured=[];original_create=character_messages.create_ack
        def create_ack(character,*args,**kwargs):
            raw=local_messages.character_unit(character=character)
            ok,n,dto,_,_=replay.unit(raw);assert ok==1 and n==len(raw)
            assert status(replay,dto+0x4c7)==dict(expected,watched=[])
            captured.append(True);return original_create(character,*args,**kwargs)
        with patch.object(character_messages,'create_ack',create_ack):
            chars.create('AchTxnB',2,'owned-txn-create-B')
        assert captured==[True]
        report['cases'].append('Pre-commit25creation DTO inherits established account scores; new character display stays empty')
        with closing(sqlite3.connect(path))as db:
            db.execute('BEGIN');before=list(db.iterdump())
            character=load_character(db,uid,1);assert character['achievement_status']==expected
            assert 'achievement_status'not in load_character(db,uid,1,identity_only=True)
            slots=current_slots(db,character);items=load_items(db,uid)
            location=dict(map=20000,board=0,progress=0,xyz=[0.,0.,0.]);balances=dict(ed=0,experience=0,revision=0)
            packet=quest_messages.reward_ack(1,character,location,slots,balances,items)
            ok,n,dto,_,_=replay.unit(packet.payload[28:]);assert ok==1 and status(replay,dto+0x4c7)==expected
            # Simulate the existing career caller's minimal after-state; the
            # shared refresh must restore current fields from this SQL writer.
            minimal={k:v for k,v in character.items()if k!='achievement_status'}
            answer=notifications(db,uid,minimal,location,character,character,False)
            packet=next(e for e in answer if e.kind==0xd9)
            ok,n,dto,_,_=replay.unit(packet.payload);assert ok==1 and status(replay,dto+0x4c7)==expected
            assert before==list(db.iterdump())
        report['cases'].append('Writer-local full load_character, questF5and career D9 preserve scores/displays; identity-only stays lightweight; reads do not write')
        for label,raw,reader,ctor,size,offset in(
            ('housing',housing_population_messages.member(character,[1.,2.,3.],items),0xda4eb0,0x2c44880,0x13d,0xa6),
            ('guild',guild_agit_messages.member(character,location,items),0xda42b0,0x2c44bc0,0x22f,0x154),
            ('dungeon/duel/wedding FullUser',dungeon_messages.member(slots,character,items),0xd9d2f0,0x7e2780,0x6b0,0x57e)):
            source,buffer=stream(replay,raw);dto=replay.alloc(size);replay.call(ctor,dto)
            assert replay.call(reader,source,dto)&255==1
            assert int.from_bytes(replay.read(buffer+32,4),'little')==len(raw)
            assert status(replay,dto+offset)==expected
            report['cases'].append(dict(member=label,original_reader=hex(reader),status_DTO_offset=hex(offset),wire_consumed=len(raw)))
    report['ok']=True
except BaseException:
    report['error']=traceback.format_exc()
    if 'replay'in locals():report['native_fault']=getattr(replay,'last_fault',None)
report['source_sha256']={str(p.relative_to(W/'source-v1')):hashlib.sha256(p.read_bytes()).hexdigest()for p in(W/'source-v1').rglob('*')if p.is_file()and '__pycache__'not in p.parts}
(W/('transactional-unit-status-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
print(json.dumps(report,ensure_ascii=False));raise SystemExit(not report['ok'])
