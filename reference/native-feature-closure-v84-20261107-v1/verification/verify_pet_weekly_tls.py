"""Two authenticated owned actors through actual pet-match request routing.



No Native Game or production data. This first network check intentionally does

not qualify task settlement, invitations or the live scene-return consumer.

"""

from pathlib import Path

from contextlib import closing

from unittest.mock import patch

import asyncio,ctypes,hashlib,json,sqlite3,ssl,struct,sys,time,traceback



K=Path(__file__).resolve().parent;W=Path('G:\\els\\analysis\\feature-closure-20261105-v1' );R=Path('G:/els');S=Path('G:\\els\\analysis\\feature-closure-20261105-v1\\release-integration-v2\\full-source')

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

        from els_server.domain.quest_flow import store as quest_store

        from els_server.protocol import quest_messages as quest_wire

        from els_server.storage.inventory_state import load_items

        def task_rows():

            with closing(sqlite3.connect(cfg.state_file))as db:

                return {t:db.execute('SELECT *FROM '+t+' ORDER BY 1').fetchall()for t in('character_quests','completed_quests','quest_actions','quest_progress_events','account_pet_battle_quest_bindings','pet_battle_results','pet_battle_quest_operations','pet_battle_quest_history')if db.execute('SELECT 1 FROM sqlite_master WHERE name=?',(t,)).fetchone()}

        def task_count():

            with closing(sqlite3.connect(cfg.state_file))as db:

                row=db.execute('SELECT objectives FROM character_quests WHERE quest=54620').fetchone()

                return None if row is None else json.loads(row[0])['54620']

        def material(uid):

            with closing(sqlite3.connect(cfg.state_file))as db:return sum(i['count']for i in load_items(db,uid)if i['template']==324815)

        primary=actors[0];primary_peer=peers[0];opponent=peers[1];current_peer=primary_peer

        stage='acceptance'

        accept=struct.pack('>ii',54620,10025);claim=struct.pack('>iiI',54620,10025,0)+b'\0\0\1\1\0'

        assert(await current_peer.query(0xee,accept)).payload==bytes(4)

        assert task_count()==0 and not material(primary['uid'])

        assert struct.unpack_from('>i',(await current_peer.query(0xf4,claim)).payload)[0]!=0

        assert task_count()==0 and not material(primary['uid'])

        report['checks'].append('Authenticated EE accepts original account54620; early F4 claim grants nothing')

        result_ids=[]

        async def battle(number):

            actors_now=(actors[0],actors[1]);live=(current_peer,opponent);sessions_now=tuple(app.playing[a['identity']['id']]for a in actors_now)

            initial={p:{kind:sum(e.kind==kind for e in p.received)for kind in(0x349,0x34b,0xa6b,0xa6f)}for p in live}

            before=facts()

            for actor,peer in zip(actors_now,live):

                body=struct.pack('>I',1)+bytes((13,0,0))+struct.pack('>iI',0,3)+b''.join(struct.pack('>QB',pet,255)for pet in actor['pets'])

                assert(await peer.query(0x342,body)).payload[:4]==bytes(4)

            for peer in live:await expect_count(peer,0x349,initial[peer][0x349]+1)

            for peer in live:await peer.send(0x34a,b'\1\1\0'+bytes(4)+b'\0');await flush(peer)

            for peer in live:await expect_count(peer,0x34b,initial[peer][0x34b]+1)

            room=flow.room(sessions_now[0]);assert room is flow.room(sessions_now[1])

            for peer in live:assert(await peer.query(0x91,struct.pack('>ii',100,0))).payload[:4]==bytes(4)

            for peer in live:await expect_count(peer,0xa6b,initial[peer][0xa6b]+1)

            rounds=0;rollback_tested=False

            while room.phase!='result':

                assert room.phase=='selecting'and rounds<20

                for index,peer in enumerate(live):

                    side=room.engine.sides[index];active=0 if side.pets[side.active].hp else next(p.uid for p in side.pets.values()if p.hp)

                    kind=1 if index==0 else 3

                    body=struct.pack('>I',3)+struct.pack('>iQ',kind,0)*3+struct.pack('>Q',active)

                    assert(await peer.query(0xa6c,body)).payload==bytes(4)

                for peer in live:await expect_count(peer,0xa6b,initial[peer][0xa6b]+2*room.engine.number)

                await live[0].send(0xa6e);await flush(live[0])

                if number==3 and room.engine.winner is not None and not rollback_tested:

                    saved=task_rows();snapshot=room.engine.snapshot();done=room.animation_done

                    with patch.object(flow,'prepare',side_effect=ValueError('owned result packet allocation failure')):

                        await live[1].send(0xa6e);await flush(live[1])

                    assert task_rows()==saved and room.engine.snapshot()==snapshot and room.animation_done==done and room.phase=='animating'

                    rollback_tested=True

                await live[1].send(0xa6e);await flush(live[1]);rounds+=1

                if room.phase=='selecting':

                    for peer in live:await expect_count(peer,0xa6b,initial[peer][0xa6b]+2*room.engine.number-1)

            for peer in live:await expect_count(peer,0xa6f,initial[peer][0xa6f]+1)

            assert room.engine.winner==actors_now[0]['uid'] and task_count()==number and facts()==before

            result_ids.append(room.seed)

            if number==3:assert rollback_tested

            for peer in live:

                assert(await peer.query(0x110)).payload==bytes(12)

                xyz=catalog()['towns']['20001']['xyz']

                assert(await peer.query(0x225,struct.pack('>iB',20001,0))).payload[:4]==bytes(4)

                assert(await peer.query(0x227,struct.pack('>fffBH',*xyz,0,0))).payload[:4]==bytes(4)

            assert not flow.rooms and not errors

            return rounds

        stage='first sealed win';rounds=[await battle(1)]

        # Switch the winning account to another owned99-level character.

        identity=primary['identity'];uid=Characters(cfg.state_file,identity['id']).create('PetWeeklyAlt',2,'pet-weekly-alt')['uid']

        LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz']);ids=[]

        with closing(sqlite3.connect(cfg.state_file))as db,db:

            db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,))

            for slot in range(3):

                pet=500000200+slot;ids.append(pet)

                db.execute('INSERT INTO companions VALUES(?,?,?,?,?,?)',(pet,uid,'pet',unit,'Alt'+str(slot),800000200+slot))

                save_pet(db,uid,dict(uid=pet,unit=unit,step=3,satiety=3840,growth=0,personality={},nutrition=0,hunger_remainder=0,digest_until=0))

        await current_peer.close()

        deadline=time.monotonic()+5

        while identity['id']in app.playing:

            assert time.monotonic()<deadline;await asyncio.sleep(.01)

        alt=dict(uid=uid,identity=identity,pets=ids,bridge=primary['bridge']);actors[0]=alt

        current_peer=await connect(alt,peers)

        view=quest_store(app.playing[identity['id']]).snapshot()

        row=next(r for r in view['active']if r['id']==54620)

        assert row['owner']==primary['uid']and row['projection_owner']==uid and row['objectives']=={54620:1}

        assert any(quest_wire.active_record(row)in e.payload for e in current_peer.received if e.kind==0x2b)

        stage='second and third sealed wins';rounds.extend((await battle(2),await battle(3)))

        assert any(e.kind==0xf3 and struct.pack('>iQ',54620,uid)in e.payload for e in current_peer.received)

        report['checks'].append('Three authenticated server-sealed random wins advance exactly1 each; cold account character switch retains canonical carrier and projects F3/2B to current UID; result encoder failure rolls back ledger/task and successful retry commits once')

        stage='fixed typed reward'

        assert(await current_peer.query(0xf4,claim)).payload[:4]==bytes(4)

        assert material(uid)==7 and material(primary['uid'])==0

        assert(await current_peer.query(0xf4,claim)).payload[:4]==bytes(4)

        assert material(uid)==7 and struct.unpack_from('>i',(await current_peer.query(0xee,accept)).payload)[0]!=0

        with closing(sqlite3.connect(cfg.state_file))as db:

            assert db.execute('SELECT COUNT(*)FROM pet_battle_results').fetchone()[0]==3

            assert db.execute('SELECT COUNT(*)FROM quest_progress_events WHERE event_id LIKE ?',( 'pet-battle-win:%',)).fetchone()[0]==3

        report['checks'].append('F4 grants original324815 x7 to current claimant once; replay and another acceptance in the completed week cannot add rewards')

        stage='weekly boundary'

        selected=quest_store(app.playing[identity['id']]);next_week=int(time.time())+7*86400

        original=task_rows()

        def encode(result):return [quest_wire.initialization(result['state'])]

        with closing(sqlite3.connect(cfg.state_file))as db:old_operation=db.execute("SELECT operation_id FROM quest_actions WHERE owner=? AND kind='accept'ORDER BY rowid LIMIT 1",(primary['uid'],)).fetchone()[0]

        try:selected.action('accept',dict(quest=54620,npc=10025),old_operation,encode,now=next_week)

        except ValueError:pass

        else:raise AssertionError('Old-week request must not reopen weekly task')

        assert task_rows()==original

        def failed_encoder(result):raise ValueError('owned next-week response failure')

        try:selected.action('accept',dict(quest=54620,npc=10025),'owned-pet-next-week-rollback',failed_encoder,now=next_week)

        except ValueError:pass

        else:raise AssertionError('Next-week encoder failure must roll back')

        assert task_rows()==original

        result=selected.action('accept',dict(quest=54620,npc=10025),'owned-pet-next-week-accept',encode,now=next_week)

        assert next(r for r in result['state']['active']if r['id']==54620)['objectives']=={54620:0}

        assert material(uid)==7

        report['checks'].append('Shared SQL action tests weekly rotation: stale prior-week operation refused; late response failure restores prior completion; fresh next-week acceptance starts0 without replaying old sealed wins')

        report.update(ok=True,rounds=rounds,errors=errors,source_pins=json.loads((Path('G:\\els\\analysis\\feature-closure-20261105-v1\\release-integration-v2\\integration-composition-v2.json')).read_bytes())['source_pins'],exclusions=['Live Native pet HUD/hit callback; task natural GUI','Invitation and trainer-token exchange'])

    except BaseException:report.update(stage=stage,error=traceback.format_exc(),errors=errors)

    finally:

        for peer in peers:

            try:await peer.close()

            except Exception as error:report.setdefault('close_errors',[]).append(type(error).__name__)

        if server is not None:await server.close()

        if app is not None:app.close()

        target=K/('integration-weekly-TLS-'+str(time.time_ns())+'.json');target.write_text(json.dumps(report,indent=2)+'\n','utf8')

        print(json.dumps(dict(ok=report['ok'],stage=report.get('stage'),checks=report['checks'],report=str(target),error=report.get('error'))))

    if not report['ok']:raise SystemExit(1)





asyncio.run(asyncio.wait_for(main(),120))

