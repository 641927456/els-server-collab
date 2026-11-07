"""Owned authenticated TLS cases for copied C1 HP identity and terminal requests."""
from pathlib import Path
import argparse,asyncio,copy,hashlib,importlib.util,json,sqlite3,struct,sys,traceback
from contextlib import closing
W=Path(__file__).resolve().parent;V=W/'variants-v1';V.mkdir(exist_ok=True)
parser=argparse.ArgumentParser();parser.add_argument('--candidate',type=Path)
parser.add_argument('--case',choices=['condition','story','old_part','combat','terminal','failed_load'],required=True)
args=parser.parse_args()
original_argv=sys.argv
sys.argv=[sys.argv[0]]+(['--candidate',str(args.candidate)]if args.candidate else[])
spec=importlib.util.spec_from_file_location('owned_reproduction_setup',W/'reproduce_tutorial_late_death.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r);sys.argv=original_argv
from els_server.domain import dungeon_flow,scene_actor_retirements,story_controller_retirements
from els_server.protocol.protocol_codec import Event
from els_server.game_data import client_data
from els_server.storage.seal_quests import ensure

def expiry(npc,owner):
    return(struct.pack('>iBQQ6fBf',npc['key'],255,2**64-1,2**64-1,*([0.]*6),1,npc['hp'])
        +bytes(4)+struct.pack('>IQB',1,owner,0)+bytes(8)+bytes(4)+bytes(8))

def economy(path):
    with closing(sqlite3.connect(path))as db:
        db.execute('BEGIN');names={x[0]for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {n:hashlib.sha256(repr(db.execute('SELECT *FROM "'+n+'" ORDER BY rowid').fetchall()).encode()).hexdigest()
                for n in ['reward_balances','reward_receipts','inventory','inventory_items']if n in names}

async def tutorial(peer,uid,stage):
    late=None
    for index in range(3):
        data=r.population(index)
        ordered=[n for n in data['npcs']if n['active']and n['key']!=data['clear_key']]+[next(n for n in data['npcs']if n['key']==data['clear_key'])]
        for n in ordered:
            late=r.probe.accepted_combat(r.emitted_npc(n,stage),uid)
            await peer.send(0xad,late);assert(await peer.until(0xae)).payload==bytes(4)
        await peer.until(0xba);await peer.send(0xbb,b'\0');await peer.until(0xbc)
        if index<2:stage=await peer.until(0xb2);await peer.send(0xb3,bytes(9));await peer.until(0xbd)
        else:await peer.until(0xc1)
    return late

async def one():
    f=r.f.FriendsTests();await f.asyncSetUp()
    result=dict(case=args.case,ok=False,candidate=args.candidate is not None,actual_Application=True,
                actual_loopback_TLS=True,production_modified=False,natural_GUI=False,natural_route=False)
    try:
        uid=r.f.Characters(f.config.state_file,f.alice['id']).create('VariantOwn',1,'owned-variant-actor')['uid']
        with closing(sqlite3.connect(f.config.state_file))as db,db:
            db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,))
            db.execute('UPDATE reward_balances SET experience=?WHERE uid=?',(client_data().thresholds[98],uid))
            ensure(db);db.execute('INSERT OR IGNORE INTO completed_quests VALUES(?,?,?,?)',(uid,26650,1,'{}'))
        peer=await f.peer(f.alice);await peer.roster()
        mid=34320 if args.case in ('condition','story','combat')else 34020 if args.case=='old_part'else 30000
        stage=await r.admit(peer,uid,mid)
        s=f.app.playing[f.alice['id']]
        assert s._c1_hp_context is not None
        result['dungeon']=mid
        if args.case in ('condition','story','old_part','combat'):
            def scene():
                run=s.dungeon_run;run._load_stage(1 if args.case=='old_part'else 3)
                run.part=1 if args.case=='old_part'else 0
                run.next=None;run.ready_at=None;run.loaded()
                s.gate_stage=run.stage;s.part_end_notified=False
                s.dungeon_substage_synced=True;s.gate_stage_loading=False;s.defeated_npcs=run.defeated
                s._c1_hp_context.check(run,emitting=True)
                if args.case in ('condition','story'):
                    for npc in run.current['npcs']:
                        if args.case=='story'and npc['template']==7513:continue
                        run.defeated[npc['key']]=expiry(npc,uid)if npc['no_drop']else r.probe.accepted_combat(npc,uid)
            await f.app.call(scene)
            result['owned_declared_scene_fixture']=True
            run=s.dungeon_run
            if args.case=='condition':
                raw=struct.pack('>iiHI',run.native_stage,run.part,0,len(run.current['conditions']))+bytes([1])*len(run.current['conditions'])+b'\1'
                request=(0x471,raw)
            elif args.case=='story':
                npc=next(n for n in run.current['npcs']if n['template']==7513)
                request=(0xad,expiry(npc,uid))
            elif args.case=='combat':
                npc=next(n for n in run.current['npcs']if n['template']==7511)
                request=(0xad,r.probe.accepted_combat(npc,uid))
            else:
                npc=next(n for n in run.parts[0]['npcs']if scene_actor_retirements.claimed_sources(type('Source',(),dict(identity=run.identity,stage=run.stage,part=0))(),n))
                result['old_actor_template']=npc['template']
                request=(0xad,expiry(npc,uid))
            before=economy(f.config.state_file);mark=peer.incoming
            await peer.send(*request);await peer.send(0x48d)
            try:
                await peer.until(0x48f);result['connection_kept']=True
            except asyncio.IncompleteReadError:
                result['connection_kept']=False
            result['events']=[e['received']for e in peer.observed if e['sequence']>=mark]
            result['errors']=[{k:d[k]for k in ['event','error']if k in d}for d in f.events if d['event']in ('protocol_error','worker_error')]
            result['economic_rows_unchanged']=economy(f.config.state_file)==before
            if args.candidate:
                assert result['connection_kept'] and not result['errors'],result
                expected=0x472 if args.case=='condition'else 0xae
                assert expected in result['events'],result
                if args.case=='condition':assert s.part_end_notified
                if args.case=='combat':
                    assert npc['key'] in s.dungeon_run.defeated
                    after=economy(f.config.state_file)
                    await peer.send(*request);assert(await peer.until(0xae)).payload==bytes(4)
                    await peer.send(0x48d);await peer.until(0x48f)
                    assert economy(f.config.state_file)==after
                    result['repeat_kill_no_additional_economic_change']=True
                else:assert result['economic_rows_unchanged']
            else:
                assert not result['connection_kept']and any(e.get('error')=='C1 HP instance lease/phase changed'for e in result['errors']),result
            result['ok']=True
        elif args.case=='failed_load':
            # Original failure closes C1 while a next B2 is awaiting B3.
            def fail():
                s.gate_stage=1;s.gate_stage_loading=True;s.dungeon_substage_synced=False
                return dungeon_flow.failed(s)
            await f.app.call(fail)
            before=economy(f.config.state_file)
            await peer.send(0xb3,bytes(9));await peer.send(0x48d)
            try:await peer.until(0x48f);result['connection_kept']=True
            except asyncio.IncompleteReadError:result['connection_kept']=False
            result['errors']=[{k:d[k]for k in ['event','error']if k in d}for d in f.events if d['event']in ('protocol_error','worker_error')]
            result['economic_rows_unchanged']=economy(f.config.state_file)==before
            result.update(ok=True,real_failure_function=True,reachability_under_review=True)
        else:
            late=await tutorial(peer,uid,stage);assert s.clear_notified
            before=economy(f.config.state_file);snap=(s.gate_stage,s.dungeon_substage_synced,s.part_end_notified,s.dungeon_clock.total,s.dungeon_clock.started)
            cases=[(0xb3,bytes(9)),(0xb8,b'\0'),(0xbb,b'\0'),(0x471,struct.pack('>iiHI',2,0,0,0)+b'\0'),(0x2ce,bytes(4))]
            details=[]
            for request in cases:
                mark=peer.incoming;await peer.send(*request);await peer.send(0x48d);await peer.until(0x48f)
                details.append(dict(kind=request[0],connection_kept=True,events=[e['received']for e in peer.observed if e['sequence']>=mark]))
            assert economy(f.config.state_file)==before
            assert(s.gate_stage,s.dungeon_substage_synced,s.part_end_notified,s.dungeon_clock.total,s.dungeon_clock.started)==snap
            assert not any(d['event']in ('protocol_error','worker_error')for d in f.events)
            await peer.send(0x67,struct.pack('>i',0x72)+bytes(96));await peer.until(0x68)
            assert s.phase=='map_loading'
            after_end=[]
            for request in [(0xad,late),(0xb3,bytes(9)),(0xb8,b'\0'),(0xbb,b'\0')]:
                await peer.send(*request);await peer.send(0x48d);await peer.until(0x48f)
                after_end.append(dict(kind=request[0],connection_kept=True))
            assert economy(f.config.state_file)==before
            assert not any(d['event']in ('protocol_error','worker_error')for d in f.events)
            result.update(ok=True,normal_tutorial_clear=True,cases=details,economic_rows_unchanged=True,
                          gate_and_clock_unchanged=True,return_to_town_loading_late_requests=after_end)
        return result
    finally:
        await f.asyncTearDown()

if __name__=='__main__':
    result={}
    try:result=asyncio.run(one())
    except BaseException:
        result=dict(ok=False,case=args.case,error=traceback.format_exc());raise
    finally:
        out=V/(args.case+('-fixed'if args.candidate else'-baseline')+'.json')
        out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
        print(json.dumps(result,ensure_ascii=True))
