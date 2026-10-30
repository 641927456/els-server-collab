"""Owned actual App/TLS admission, synthetic native deaths, real D0 and SQL."""
from pathlib import Path
from contextlib import closing
import ast,asyncio,hashlib,importlib.util,json,os,sqlite3,struct,sys,tempfile,traceback,types,uuid
R=Path('G:/els');O=Path(__file__).resolve().parent;tempfile.tempdir=str(O.parent/'tmp');sys.dont_write_bytecode=True
LOCAL='--local' in sys.argv
BASE=R/('releases/local/local-dungeon-populations-20261031-v1' if LOCAL else 'releases/online/dungeon-populations-20261031-v1');sys.path[:0]=[str(BASE),str(R/'tools')]
import els_server.domain,els_server.storage
candidate=O/'candidate' if (O/'candidate').is_dir() else O/'source/shared'
variant=(O/'local-variant' if LOCAL else candidate) if (O/'candidate').is_dir() else O/('source/local' if LOCAL else 'source/online')
els_server.domain.__path__.insert(0,str(candidate/'els_server/domain'))
if variant!=candidate:els_server.domain.__path__.insert(0,str(variant/'els_server/domain'))
els_server.storage.__path__.insert(0,str(candidate/'els_server/storage'))
from els_server.domain import native_script_loot as rules
rules.secrets=types.SimpleNamespace(randbelow=lambda bound:0)
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
    regions=region_catalog().data['dungeons']['33891'];reqs={region_catalog().data['regions'][str(x)]['requirement'].get('RequireQuestID')for x in regions}-{0,None}
    with closing(sqlite3.connect(c.config.state_file)) as db,db:
        db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,));db.executemany('INSERT OR IGNORE INTO completed_quests VALUES(?,?,?,?)',[(uid,q,1,'{}')for q in reqs])
    if not LOCAL:peer=await c.peer(account)
    else:
        class Loopback:
            async def remote(self):return await asyncio.open_connection('127.0.0.1',c.port)
        peer=await Peer.open(Loopback());c.peers.append(peer)
    await peer.roster();await peer.enter_town(uid)
    await peer.send(0x7d4,struct.pack('>ii',1,33891));reply=await peer.until(0x7d5);assert struct.unpack_from('>i',reply.payload)[0]==0
    mode=struct.unpack_from('>i',reply.payload,4)[0];kind=0x37f if mode==2 else 0x382
    await peer.send(kind,ENTRY);entry=await peer.until(0x380 if kind==0x37f else 0x383);assert struct.unpack_from('>i',entry.payload)[0]==0
    await peer.until(0x14a);await peer.send(0x91,struct.pack('>ii',100,0));await peer.until(0xb2)
    s=c.app.playing[account['id']] if not LOCAL else OBSERVED[-1];clock=[0.];s.dungeon_run.clock=lambda:clock[0]
    await peer.send(0xb3,bytes(9));await peer.until(0xbd)
    return s,clock

def advance(s,clock,*,stop_boss=False):
    uid=s.account.uid
    for _ in range(100):
        run=s.dungeon_run
        if stop_boss and (run.stage,run.part)==(4,0):return
        for n in list(run.current['npcs']):
            if n.get('team',1)==0 or n['template']==2368:continue
            replies=s.handle(death(n,uid));assert replies and replies[0].kind==0xae,(n,replies)
        clock[0]+=max([x['seconds']+x['delay']for x in run.current['conditions']]+[0])+1
        s.next_periodic=0;s.periodic_notifications();clock[0]=max(clock[0],run.ready_at or 0)+1;s.next_periodic=0;s.periodic_notifications()
        assert s.part_end_notified,(run.stage,run.part)
        reply=s.handle(Event(0x202,kind=0xbb,payload=struct.pack('>b',run.part)))
        if s.clear_notified:assert any(e.kind==0xc1 for e in reply);return
        if s.gate_stage_loading:s.handle(Event(0x202,performers=(0,),kind=0xb3,payload=bytes(9)))
    raise AssertionError('Traversal bound')

def check_claim(s,path):
    drop=next(d for d in s.world_drops.values() if d.get('source')==rules.POLICY)
    before=s.account.get_inventory_snapshot();event=pickup(drop);reply=s.handle(event)
    assert [e.kind for e in reply]==[0xd1,0xd2,0xd3],([e.kind for e in reply],rules._bound(s))
    after=s.account.get_inventory_snapshot();assert sum(i['template']==30572 for i in after['items'])==1
    repeat=s.handle(event);assert [e.kind for e in repeat]==[0xd1,0xd3];assert s.account.get_inventory_snapshot()==after
    from els_server.storage.inventory_state import InventoryState
    assert InventoryState(path,s.account.uid).snapshot()==after
    return dict(pickup_kinds=[e.kind for e in reply],repeat_kinds=[e.kind for e in repeat],cold_read=True,new_item=next(i for i in after['items']if i['template']==30572))

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
    out=dict(ok=False,actual_App=True,TLS_admission=not LOCAL,local_mode=LOCAL,synthetic_deaths=True,natural_battle=False,rows=[])
    try:
        for index,timing in enumerate(('before-boss','after-boss','after-clear','bad-ending')):
            row=dict(timing=timing,ok=False);out['rows'].append(row)
            try:
                s,clock=await admit(c,index)
                def exercise():
                    advance(s,clock,stop_boss=True);dummy=rules._actor(s.dungeon_run);event=death(dummy,0)
                    # Call the explicit source validator as well as the real dispatcher,
                    # so unexpected implementation errors remain visible in this test.
                    bound=rules._bound(s)
                    with closing(sqlite3.connect(c.config.state_file))as db,db:db.execute('BEGIN');rules._validate(db,s,bound)
                    if timing=='before-boss':
                        reply=s.handle(event);assert [e.kind for e in reply]==[0xae,0xaf,0xcf],[e.kind for e in reply]
                    if timing=='after-boss':
                        boss=next(n for n in s.dungeon_run.current['npcs'] if n['template']==2363)
                        assert s.handle(death(boss,s.account.uid))[0].kind==0xae
                        reply=s.handle(event);assert [e.kind for e in reply]==[0xae,0xaf,0xcf],[e.kind for e in reply]
                    advance(s,clock);assert s.clear_notified
                    if timing=='after-clear':
                        bound=rules._bound(s)
                        with closing(sqlite3.connect(c.config.state_file))as db,db:db.execute('BEGIN');rules._validate(db,s,bound)
                        reply=s.handle(event);assert [e.kind for e in reply]==[0xae,0xaf,0xcf],[e.kind for e in reply]
                    if timing=='bad-ending':assert not any(d.get('source')==rules.POLICY for d in s.world_drops.values())
                    else:
                        old=s.world_drop_sequence;assert [e.kind for e in s.handle(event)]==[0xae];assert old==s.world_drop_sequence
                        row.update(check_claim(s,c.config.state_file))
                    with closing(sqlite3.connect(c.config.state_file))as db:
                        assert db.execute('SELECT COUNT(*) FROM reward_receipts WHERE run_id=?',(s.reward_run_id,)).fetchone()==(1,)
                    row['C1']=True;row['ok']=True
                await c.app.call(exercise)
            except Exception as e:row.update(error=repr(e),traceback=traceback.format_exc(limit=12))
        out['ok']=all(r['ok']for r in out['rows'])
    finally:
        await c.asyncTearDown();out['private_environment_closed']=True
        (O/('script-reward-qualification-local.json' if LOCAL else 'script-reward-qualification.json')).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(out,ensure_ascii=False,indent=2))

OBSERVED=[]
if __name__=='__main__':asyncio.run(main())
