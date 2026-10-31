"""Owned actual App/TLS admission, synthetic native deaths, real D0 and SQL."""
from pathlib import Path
from contextlib import closing
import ast,asyncio,hashlib,importlib.util,json,os,sqlite3,struct,sys,tempfile,traceback,types,uuid
R=Path('G:/els');O=Path(__file__).resolve().parent;tempfile.tempdir=str(O.parent/'tmp');sys.dont_write_bytecode=True
LOCAL='--local' in sys.argv
BASE=Path('G:\\els\\releases\\online\\collection-synergy-economy-20261031-v1') if not LOCAL else Path('G:\\els\\releases\\local\\local-collection-synergy-economy-20261031-v1')
sys.path[:0]=[str(BASE),str(R/'tools')]
import els_server.domain
els_server.domain.__path__.insert(0,str(O/'candidate/els_server/domain'))
from els_server.domain import dungeon_loot_catalog as rules
assert len(rules.catalog()['maps'])==22
from els_server.protocol.protocol_codec import Event,encode_event,encode_frame
from els_server.storage.characters import Characters
from els_server.storage.seal_quests import QuestState
from els_server.domain.region_quests import region_catalog
from els_server.domain.town_travel import catalog as towns
from els_server.game_data import client_data
os.environ['ELS_TEST_CERT_DIR']=str(R/'analysis/luciel-natural-dynamic-passive-01a1531c-20261020-v1/party-UI-r10/tls')
spec=importlib.util.spec_from_file_location('owned_private_peer',R/'tests/test_friends_server.py');t=importlib.util.module_from_spec(spec);sys.modules[spec.name]=t;spec.loader.exec_module(t)
prior=R/'analysis/monster-economy-formal-20261025-v1/verify_native.py'
nodes=[n for n in ast.parse(prior.read_text('utf8')).body if isinstance(n,ast.ClassDef)and n.name=='Peer']
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(prior),'exec'));t.Peer=Peer
ENTRY=bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947')
source=json.loads((R/'analysis/client-6c6b5180/20261014-002737/world-drop-probe-snapshot.json').read_bytes())
WIRE=bytes.fromhex(next(e['payload_hex'] for e in source['server'] if e.get('kind')==0xd0 and e.get('event')=='decoded_client_event'))

def death(n,uid):
    return Event(0x202,performers=(0,),kind=0xad,payload=struct.pack('>iBQQ6fBf',n['key'],1,uid,uid,0,0,0,0,0,0,0,n['hp'])+struct.pack('>IIQIQ',0,0,0,0,uid))

def pickup(drop):
    from els_server.domain.drop_pickup import native_modes
    out=b''
    for spec in native_modes()[4]['fields']:
        k=spec['field'];mask=spec.get('xor',0)
        if k=='item':out+=struct.pack('>I',drop['template'])+WIRE[4:320]
        elif k=='opaque':out+=struct.pack('>I',3)+b'abc'
        elif k=='drop_id':out+=struct.pack('>I',drop['drop_id']^mask)
        elif k=='flag':out+=bytes([mask])
        else:out+=struct.pack('>3f',*drop['xyz'])
    return Event(0x202,performers=(0,),kind=0xd0,payload=out)

async def admit(c,index):
    account=c.app.registry.create('trueend'+uuid.uuid4().hex[:10]) if not LOCAL else {'id':1};uid=Characters(c.config.state_file,account['id']).create('TE'+str(index),1,'audit:'+str(index))['uid']
    QuestState(c.config.state_file,uid,account_id=account['id']).snapshot()
    regions=region_catalog().data['dungeons']['33232'];reqs={region_catalog().data['regions'][str(x)]['requirement'].get('RequireQuestID')for x in regions}-{0,None}
    with closing(sqlite3.connect(c.config.state_file)) as db,db:
        db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,));db.executemany('INSERT OR IGNORE INTO completed_quests VALUES(?,?,?,?)',[(uid,q,1,'{}')for q in reqs])
    if not LOCAL:peer=await c.peer(account)
    else:
        class Loopback:
            async def remote(self):return await asyncio.open_connection('127.0.0.1',c.port)
        peer=await Peer.open(Loopback());c.peers.append(peer)
    await peer.roster();await peer.enter_town(uid)
    await peer.send(0x7d4,struct.pack('>ii',1,33232));reply=await peer.until(0x7d5);assert struct.unpack_from('>i',reply.payload)[0]==0
    mode=struct.unpack_from('>i',reply.payload,4)[0];kind=0x37f if mode==2 else 0x382
    await peer.send(kind,ENTRY);entry=await peer.until(0x380 if kind==0x37f else 0x383);assert struct.unpack_from('>i',entry.payload)[0]==0
    await peer.until(0x14a);await peer.send(0x91,struct.pack('>ii',100,0));await peer.until(0xb2)
    s=c.app.playing[account['id']] if not LOCAL else OBSERVED[-1];clock=[0.];s.dungeon_run.clock=lambda:clock[0]
    await peer.send(0xb3,bytes(9));await peer.until(0xbd)
    return s,clock

async def main():
    c=t.FriendsTests();await c.asyncSetUp()
    if LOCAL:
        await c.server.close();c.app.close()
        from els_server.config import ServerConfig
        from els_server.application import Application
        from els_server.transport import GameServer
        from els_server.storage.lifecycle import prepare_database
        c.config=ServerConfig(mode='local',port=0,state_file=c.root/'local.sqlite3',log_dir=c.root/'logs-local')
        prepare_database(c.config.state_file);c.app=Application(c.config);await c.app.start();c.server=GameServer(c.config,c.app,lambda *x,**y:None);_,c.port=await c.server.start()
        original=c.app.session
        async def observe(*args,**kwargs):
            session=await original(*args,**kwargs);OBSERVED.append(session);return session
        c.app.session=observe
    out=dict(ok=False,channel='local'if LOCAL else'online',actual_App=True,TLS_admission=not LOCAL,canonical_native_expiry=True,natural_battle=False)
    try:
        s,clock=await admit(c,0)
        def exercise():
            from els_server.domain import dungeon_flow as flow
            spec=importlib.util.spec_from_file_location('own_installed_flow',BASE/'els_server/domain/dungeon_flow.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
            run=s.dungeon_run;actor=next(n for n in run.current['npcs']if n['template']==1229)
            assert actor['active']is False and actor['no_drop']is True
            def packet(*,key=actor['key'],hp=2152920,owner=s.account.uid,source=2**64-1,status=1):
                data=struct.pack('>iBQQ6fBf',key,255,source,source,0,0,0,1440,45391,10127,status,hp)
                data+=struct.pack('>IIQBQIQ',0,1,owner,0,0,0,0)
                return Event(0x202,performers=(0,),kind=0xad,payload=data)
            event=packet();before=s.account.get_inventory_snapshot();drops=dict(s.world_drops);sequence=s.world_drop_sequence;defeated=dict(run.defeated)
            assert old.handle(s,event)==[] and run.defeated==defeated
            replies=s.handle(event);assert[e.kind for e in replies]==[0xae,0xaf],[e.kind for e in replies]
            assert run.defeated[actor['key']]==event.payload and actor['active']is False and not s.part_end_notified
            assert s.account.get_inventory_snapshot()==before and s.world_drops==drops and s.world_drop_sequence==sequence
            assert[e.kind for e in s.handle(event)]==[0xae]
            from els_server.storage.inventory_state import InventoryState
            assert InventoryState(c.config.state_file,s.account.uid).snapshot()==before
            negatives=[]
            for name,ev in [('foreign_readiness',packet(owner=s.account.uid+1)),('participant_as_script_source',packet(source=s.account.uid)),('zero_HP',packet(hp=0)),('wrong_status',packet(status=0)),('wrong_instance',packet(key=79))]:
                assert flow.handle(s,ev)==[],name;negatives.append(name)
            for field,value in [('active',True),('no_drop',False),('source_index',None),('boss',True)]:
                prior=actor.get(field);actor[field]=value
                try:assert flow.handle(s,event)==[],field
                finally:
                    if prior is None:actor.pop(field,None)
                    else:actor[field]=prior
                negatives.append('category:'+field)
            actor['dynamic']=True
            try:assert [e.kind for e in flow.handle(s,event)]==[e.kind for e in old.handle(s,event)]==[0xae]
            finally:actor.pop('dynamic')
            original=s.reward_run_id;s.reward_run_id=str(uuid.uuid4())
            try:assert flow.handle(s,event)==[]
            finally:s.reward_run_id=original
            negatives.append('other_run')
            assert s.account.get_inventory_snapshot()==before and s.world_drops==drops
            # Actual normal room completion; a report during the next B3 barrier is refused.
            for npc in list(run.current['npcs']):
                if npc['key']not in run.defeated:
                    assert s.handle(death(npc,s.account.uid))[0].kind==0xae
            clock[0]+=1;s.next_periodic=0;s.periodic_notifications();assert s.part_end_notified
            s.handle(Event(0x202,kind=0xbb,payload=struct.pack('>b',run.part)))
            assert not s.dungeon_substage_synced and flow.handle(s,event)==[]
            return dict(no_EXP_ED_loot_or_inventory_change=True,no_early_room_end=True,repeated_ack_only=True,cold_read=True,negative_cases=negatives,stage_loading_replay_refused=True)
        out.update(await c.app.call(exercise));out['ok']=True
    except Exception as error:out.update(error=repr(error),traceback=traceback.format_exc(limit=13))
    finally:
        await c.asyncTearDown();out['private_environment_closed']=True
        (O/('inactive-expiry-qualification-local.json'if LOCAL else'inactive-expiry-qualification-online.json')).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(out,ensure_ascii=False,indent=2))
OBSERVED=[]
if __name__=='__main__':asyncio.run(main())
