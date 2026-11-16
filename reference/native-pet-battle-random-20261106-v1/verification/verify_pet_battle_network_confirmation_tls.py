"""Two authenticated owned actors through actual pet-match request routing.

No Native Game or production data. This first network check intentionally does
not qualify task settlement, invitations or the live scene-return consumer.
"""
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import asyncio,ctypes,hashlib,json,sqlite3,ssl,struct,sys,time,traceback

K=Path(__file__).resolve().parent;W=K.parent;R=Path('G:/els');S=K/'network-source-v1'
sys.dont_write_bytecode=True
sys.path[:0]=[str(S),str(R/'tools'),str(R/'tools/pylibs'),str(R),str(W/'delivery-duel-v1')]
ctypes.WinDLL(str(W/'duel-wire-v2/full-source/python/sqlite3.dll'))
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.companion_state import ensure as companions
from els_server.storage.pet_progression import save as save_pet
from els_server.domain.pet_progression import catalog as pet_catalog
from els_server.domain.town_travel import catalog
from create_friends_certificate import create
from native_peer import connect


async def flush(peer):
    await peer.send(0x48d);await peer.until(0x48f)


async def expect_count(peer,kind,count):
    while sum(e.kind==kind for e in peer.received)<count:await peer.until(kind)


async def main():
    report=dict(ok=False,actual_authenticated_TLS=True,native_Game=False,natural_GUI=False,
        production_database_access=False,task_writer_qualified=False,checks=[])
    private=K/'tls-network-v1'/str(time.time_ns());private.mkdir(parents=True);create(private,'127.0.0.1')
    cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=private/'game.sqlite3',
        accounts_file=private/'accounts.sqlite3',tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
    app=server=None;peers=[];errors=[];stage='setup'
    try:
        app=Application(cfg);await app.start();actors=[]
        templates=pet_catalog()['templates'];unit=next(int(k)for k,v in templates.items()if v['EVOLUTION_ALL_STEP']==3 and not 20000<=int(k)<=25000)
        for index in range(2):
            identity=app.registry.create('ownedpetnet'+str(index))
            uid=Characters(cfg.state_file,identity['id']).create('PetNet'+str(index),1,'owned-pet-net-'+str(index))['uid']
            LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
            ids=[]
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,));companions(db)
                for slot in range(3):
                    pet=500000100+index*10+slot;ids.append(pet)
                    db.execute('INSERT INTO companions VALUES(?,?,?,?,?,?)',(pet,uid,'pet',unit,'Own'+str(slot),800000100+index*10+slot))
                    value=dict(uid=pet,unit=unit,step=3,satiety=3840,growth=0,personality={},nutrition=0,hunger_remainder=0,digest_until=0)
                    save_pet(db,uid,value)
            actors.append(dict(uid=uid,identity=identity,pets=ids))
        server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
        _,port=await server.start()
        for actor in actors:
            identity=actor['identity'];actor['bridge']=dict(host='127.0.0.1',port=port,name=identity['name'],token=identity['token'],
                certificate_sha256=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest())
            await connect(actor,peers)
        sessions=tuple(app.playing[a['identity']['id']]for a in actors);flow=app.world.pet_battles
        def facts():
            with closing(sqlite3.connect(cfg.state_file))as db:
                return {table:db.execute('SELECT *FROM '+table+' ORDER BY 1').fetchall()for table in('reward_balances','inventory_items','companions','pet_progression')}
        baseline=facts();stage='registration'
        for actor,peer in zip(actors,peers):
            body=struct.pack('>I',1)+bytes((13,0,0))+struct.pack('>iI',0,3)+b''.join(struct.pack('>QB',pet,255)for pet in actor['pets'])
            assert(await peer.query(0x342,body)).payload[:4]==bytes(4)
        for peer in peers:await flush(peer)
        for peer in peers:await expect_count(peer,0x349,1)
        assert all(any(e.kind==0x349 for e in p.received)for p in peers)
        assert flow.offers[sessions[0]]is flow.offers[sessions[1]]
        consent=b'\1\1\0'+bytes(4)+b'\0'
        await peers[0].send(0x34a,consent);await flush(peers[0])
        await peers[1].send(0x34a,consent)
        for peer in peers:await flush(peer)
        room=flow.room(sessions[0]);assert room is not None and flow.room(sessions[1])is room
        assert room.phase=='loading' and not flow.queue and not flow.offers
        for peer in peers:await expect_count(peer,0x34b,1)
        assert all(any(e.kind==0x34b for e in p.received)for p in peers)
        report['checks'].append('two current distinct authenticated99-level actors:342/343/344 ->349 ->both34A ->34B pet room and private relay epoch')
        from els_server.domain.pet_battle_scene import descriptor,spawn as scene_spawn
        from els_server.domain.dungeon_npcs import encode_npc
        scene_payload=struct.pack('>I',2)+b''.join(encode_npc(bytearray(descriptor(t)),0)for t in(3266,3265))
        assert(await peers[1].query(0x2ce,scene_payload)).payload==struct.pack('>i',1)
        assert room.scene is None and room.phase=='loading'
        assert(await peers[0].query(0x2ce,scene_payload[:-1])).payload==struct.pack('>i',1)
        assert room.scene is None
        assert(await peers[0].query(0x2ce,scene_payload)).payload==bytes(4)
        assert room.scene is not None and not room.scene_sent
        for peer in peers:await flush(peer)
        assert all(not any(e.kind==0x2d0 for e in p.received)for p in peers)
        assert(await peers[0].query(0x2ce,scene_payload)).payload==bytes(4)
        report['checks'].append('Pet scene request requires admitted host and exact original pair; malformed/foreign request creates nothing; loading defers actor publication and duplicate request creates no second pair')
        stage='loading'
        for peer in peers:assert(await peer.query(0x91,struct.pack('>ii',100,0))).payload[:4]==bytes(4)
        for peer in peers:await flush(peer)
        assert room.phase=='selecting' and all(s.phase=='pet_selecting'for s in sessions)
        for peer in peers:
            await expect_count(peer,0x96,1);await expect_count(peer,0xa6b,1)
        assert all(any(e.kind==0x96 for e in p.received)and any(e.kind==0xa6b for e in p.received)for p in peers)
        assert all(next(i for i,e in enumerate(p.received)if e.kind==0x96)<next(i for i,e in enumerate(p.received)if e.kind==0xa6b)for p in peers)
        original=room.engine.snapshot(),room.phase,dict(flow.rooms)
        for peer in peers:
            await peer.send(0x34a,consent);await flush(peer)
        assert original==(room.engine.snapshot(),room.phase,dict(flow.rooms))and not errors
        assert not app.world.pvp.registrations.offers and not app.world.pvp.registrations.queue
        report['checks'].append('Repeated native34A after pet admission remains in this room; no duplicate admission, combat mutation, normal-PvP queue or worker error')
        assert room.scene_sent
        for peer in peers:
            await expect_count(peer,0x2d0,1)
            kinds=[e.kind for e in peer.received]
            assert kinds.index(0x96)<kinds.index(0x2d0)<kinds.index(0xa6b)
        assert(await peers[0].query(0x2ce,scene_payload)).payload==bytes(4)
        for peer in peers:await flush(peer)
        assert all(sum(e.kind==0x2d0 for e in p.received)==1 for p in peers)
        report['checks'].append('Both load100s publish96 then one scene2D0 before initialA6B; exact retry ACK creates no duplicate actor or combat mutation')
        assert flow.manifest(app,actors[0]['identity']['id'])['epoch']==room.seed
        assert flow.relay_target(app,actors[0]['identity']['id'],room.seed,actors[1]['uid'])==(actors[1]['identity']['id'],actors[0]['uid'])
        assert flow.relay_target(app,actors[0]['identity']['id'],room.seed,999999)is None
        report['checks'].append('both91/92/93 complete before96 and initialA6B; original session/epoch routes only the admitted peer')
        def attack(active):return struct.pack('>I',3)+struct.pack('>iQ',1,0)*3+struct.pack('>Q',active)
        def unchanged():return room.engine.snapshot(),room.engine.phase,dict(room.requests)
        before=unchanged()
        assert(await peers[0].query(0xa6c,attack(999999))).payload==struct.pack('>i',-1)
        assert unchanged()==before
        room.deadline=time.monotonic()-1
        before=unchanged()
        with patch('els_server.domain.pet_battle_flow.notice',side_effect=ValueError('owned timeout late encoder failure')):
            try:flow.periodic(sessions[0])
            except ValueError:pass
            else:raise AssertionError('Timeout encoder should fail before publication')
        assert unchanged()==before and room.phase=='selecting'
        flow.periodic(sessions[0]);assert room.phase==room.engine.phase=='animating'
        after=unchanged();flow.periodic(sessions[1]);assert unchanged()==after
        for peer in peers:await expect_count(peer,0xa6b,2)
        for peer in peers:await peer.send(0xa6e);await flush(peer)
        for peer in peers:await expect_count(peer,0xa6b,3)
        assert room.phase==room.engine.phase=='selecting'and room.engine.number==2
        report['checks'].append('Real deadline timeout fills both absent plans, publishes A6B and animating phase once; late encoder failure rolls back, second periodic is inert, both A6E start next round')
        first=attack(0)
        assert(await peers[0].query(0xa6c,first)).payload==bytes(4)
        before=unchanged();second=attack(0)
        with patch('els_server.domain.pet_battle_flow.notice',side_effect=ValueError('owned late projection failure')):
            assert(await peers[1].query(0xa6c,second)).payload==struct.pack('>i',-1)
        assert unchanged()==before
        assert(await peers[1].query(0xa6c,second)).payload==bytes(4)
        assert room.phase=='animating'
        before=unchanged();assert(await peers[0].query(0xa6c,first)).payload==bytes(4);assert unchanged()==before
        report['checks'].append('foreign active UID refused; failed late round encoder leaves the source match unchanged; exact completed selection replay changes no HP or budget')
        stage='battle'
        rounds=0
        while room.phase!='result':
            assert rounds<20
            if room.phase=='selecting':
                for index,peer in enumerate(peers):
                    side=room.engine.sides[index]
                    active=0 if side.pets[side.active].hp else next(p.uid for p in side.pets.values()if p.hp)
                    assert(await peer.query(0xa6c,attack(active))).payload==bytes(4)
            assert room.phase=='animating'
            for peer in peers:await expect_count(peer,0xa6b,2*room.engine.number)
            for peer in peers:await peer.send(0xa6e);await flush(peer)
            for peer in peers:await flush(peer)
            rounds+=1
            if room.phase=='selecting':
                for peer in peers:await expect_count(peer,0xa6b,2*room.engine.number-1)
        winner=room.engine.winner
        assert winner in{a['uid']for a in actors}
        loser=next(side for side in room.engine.sides if side.uid!=winner)
        assert all(p.hp==0 for p in loser.pets.values())
        for peer in peers:await expect_count(peer,0xa6f,1)
        assert all(any(e.kind==0xa6f and struct.unpack_from('>Q',e.payload,2)[0]==winner for e in p.received)for p in peers)
        assert facts()==baseline
        report['checks'].append('actual authenticatedA6C/A6D ->A6B ->bothA6E advances rounds; server-owned all-three-pets-fainted result emitsA6F with no XP/ED/AP/inventory/pet-state change')
        stage='return'
        for peer in peers:
            assert(await peer.query(0x110)).payload==bytes(12)
            xyz=catalog()['towns']['20001']['xyz']
            assert(await peer.query(0x225,struct.pack('>iB',20001,0))).payload[:4]==bytes(4)
            assert(await peer.query(0x227,struct.pack('>fffBH',*xyz,0,0))).payload[:4]==bytes(4)
        assert not flow.rooms and all(s.phase=='town_ready'for s in sessions)
        assert facts()==baseline and not errors
        report['checks'].append('authenticated110/111 and ordinary225/227 return both actors to their saved town; no room/queue remains')
        report.update(ok=True,rounds=rounds,errors=errors,source_pins=json.loads((K/'network-composition-v9.json').read_bytes())['source_pins'],
            exclusions=['Task ledger/progress/reward and invitation branch','Natural Native pet lobby/scene/15-second delivery allowance/result return','Disconnect remains a separate case'])
    except BaseException:report.update(stage=stage,error=traceback.format_exc(),errors=errors)
    finally:
        for peer in peers:
            try:await peer.close()
            except Exception as error:report.setdefault('close_errors',[]).append(type(error).__name__)
        if server is not None:await server.close()
        if app is not None:app.close()
        target=K/('network-TLS-'+str(time.time_ns())+'.json');target.write_text(json.dumps(report,indent=2)+'\n','utf8')
        print(json.dumps(dict(ok=report['ok'],stage=report.get('stage'),checks=report['checks'],report=str(target),error=report.get('error'))))
    if not report['ok']:raise SystemExit(1)


asyncio.run(main())
