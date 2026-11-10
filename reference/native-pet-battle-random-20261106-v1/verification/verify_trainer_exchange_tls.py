"""Original seven exchanges over authenticated TLS, economic rollback/replay and usable outputs."""
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import asyncio,ctypes,hashlib,json,sqlite3,ssl,struct,sys,time,traceback
K=Path(__file__).resolve().parent;W=K.parent;R=Path('G:/els');S=K/'reward-source-v1'
sys.dont_write_bytecode=True;sys.path[:0]=[str(S),str(R/'tools'),str(R/'tools/pylibs'),str(R),str(W/'delivery-duel-v1')]
ctypes.WinDLL(str(W/'duel-wire-v2/full-source/python/sqlite3.dll'))
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.companion_state import ensure as companions,rows as pet_rows
from els_server.storage.pet_progression import save as save_pet
from els_server.domain.pet_progression import catalog as pet_catalog
from els_server.domain.town_travel import catalog as towns
from els_server.domain.pet_trainer_exchange import catalog,recipe,source_factory,SOURCE_ONLY
from els_server.domain.pet_trainer_exchange_flow import handle
from els_server.storage.inventory_state import load_items,grant_items
from els_server.protocol.protocol_codec import Event
from create_friends_certificate import create
from native_peer import connect

async def main():
    report=dict(ok=False,actual_authenticated_TLS=True,native_Game=False,natural_GUI=False,production_database_access=False,checks=[])
    private=K/'trainer-TLS-v1'/str(time.time_ns());private.mkdir(parents=True);create(private,'127.0.0.1')
    cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
    app=server=None;peers=[];errors=[];stage='setup'
    try:
        app=Application(cfg);await app.start();actors=[]
        unit=next(int(k)for k,v in pet_catalog()['templates'].items()if v['EVOLUTION_ALL_STEP']==3 and not 20000<=int(k)<=25000)
        for index in range(2):
            identity=app.registry.create('ownedtrainer'+str(index));uid=Characters(cfg.state_file,identity['id']).create('TrainerOwn'+str(index),1,'own-trainer-'+str(index))['uid']
            LocalState(cfg.state_file,uid).save(20001,0,0,towns()['towns']['20001']['xyz'])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,));companions(db)
                pet=500000100+index;db.execute('INSERT INTO companions VALUES(?,?,?,?,?,?)',(pet,uid,'pet',unit,'Own',800000100+index))
                save_pet(db,uid,dict(uid=pet,unit=unit,step=3,satiety=1000,growth=0,personality={},nutrition=0,hunger_remainder=0,digest_until=int(time.time())+20000))
                db.execute('INSERT INTO companion_active VALUES(?,?,0,0)',(uid,pet))
                if index==0:db.execute('INSERT INTO inventory_items VALUES(?,?,?,?,?,?,?)',(8000001,uid,324815,2,15,4,0))
            actors.append(dict(uid=uid,identity=identity,pet=pet))
        server=GameServer(cfg,app,lambda event,**kw:errors.append(event)if event in('protocol_error','worker_error','notification_error','connection_task_error')else None);_,port=await server.start()
        for actor in actors:
            identity=actor['identity'];actor['bridge']=dict(host='127.0.0.1',port=port,name=identity['name'],token=identity['token'],certificate_sha256=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest());await connect(actor,peers)
        owner=actors[0]['uid'];account=actors[0]['identity']['id'];session=app.playing[account];peer=peers[0]
        def items():
            with closing(sqlite3.connect(cfg.state_file))as db:return load_items(db,owner)
        def facts():
            with closing(sqlite3.connect(cfg.state_file))as db:return {t:db.execute('SELECT *FROM '+t+' ORDER BY 1').fetchall()for t in('inventory_items','reward_balances','pet_progression')}
        def item(t):return next(i for i in items()if i['template']==t)
        def count(t):return sum(i['count']for i in items()if i['template']==t)
        def event(payload):return Event(0x202,kind=0x223,payload=payload,performers=(0,))
        def payload(a):return struct.pack('>iQiiiiiBi',40016,0,324815,a[7]['m_iSourceQuantity'],a[4]if a[2]==3 else 0,a[2],1,1,0)
        def guard(db):
            assert Path(db.execute('PRAGMA database_list').fetchone()[2]).resolve()==cfg.state_file.resolve()
            from els_server.storage.item_actor import require_active_character
            from els_server.storage.profession_state import require_owner
            require_active_character(db,owner);require_owner(db,owner,account)
        stage='exchange'
        base=facts();first=catalog()['recipes'][0]['arguments'];body=payload(first)
        assert(await peers[1].query(0x223,body)).payload[:4]==struct.pack('>i',-1)and facts()==base
        with patch('els_server.storage.material_exchange.encode_event',side_effect=ValueError('own late exchange encoding failure')):
            assert(await peer.query(0x223,body)).payload[:4]==struct.pack('>i',-1)
        assert facts()==base
        report['checks'].append('Foreign account without tokens and late encoder failure produce no inventory, ED or pet-state increment')
        for record in catalog()['recipes']:
            a=record['arguments'];body=payload(a);before=count(a[4]);tokens=count(324815);sequence=peer.outgoing
            reply=await peer.query(0x223,body);assert reply.payload[:4]==bytes(4),(a[4],reply.payload[:4].hex(),errors)
            assert count(a[4])==before+a[5]and count(324815)==tokens-a[7]['m_iSourceQuantity']
            assert reply.payload[-17]==a[2]
            saved=facts();assert handle(session,event(body),sequence)[0].payload[:4]==bytes(4)and facts()==saved
        assert count(324815)==3
        for t in SOURCE_ONLY:
            try:
                with closing(sqlite3.connect(cfg.state_file))as db,db:
                    db.execute('BEGIN IMMEDIATE');grant_items(db,[dict(template=t,metadata=2,group=item(t)['group'],quantity=1)],owner)
            except ValueError:pass
            else:raise AssertionError('Unqualified generic output '+str(t))
        report['checks'].append('All seven original223/224 recipes debit exact tokens and issue exact outputs; receipt replay and unqualified grants cannot duplicate awards')
        stage='resurrection'
        from els_server.storage.resurrection_counter import count as revives
        with closing(sqlite3.connect(cfg.state_file))as db:before=revives(db,owner)
        box=item(160164);assert(await peer.query(0x559,struct.pack('>iIBB',160164,0,0,0))).payload[:4]==bytes(4)
        box_payload=struct.pack('>QBBBIi',box['uid'],0,0,0,0,0);sequence=peer.outgoing
        assert(await peer.query(0x196,box_payload)).payload[:4]==bytes(4)
        with closing(sqlite3.connect(cfg.state_file))as db:assert revives(db,owner)==before+3
        from els_server.storage.fixed_cubes import open_cube
        open_cube(cfg.state_file,owner,160164,box_payload,session.shop_session_id+':'+str(owner)+':'+str(sequence),account_id=account,prepare=guard)
        with closing(sqlite3.connect(cfg.state_file))as db:assert revives(db,owner)==before+3
        assert count(160164)==0
        report['checks'].append('Exchanged160164 opens through original559/560 and196/197 and adds exactly three native revives')
        stage='digest'
        before=count(135980)
        with closing(sqlite3.connect(cfg.state_file))as db:old=pet_rows(db,owner,'pet')[0]['digest_until']
        assert(await peer.query(0x8b9,struct.pack('>Qi',actors[0]['pet'],135980))).payload[:4]==bytes(4)
        with closing(sqlite3.connect(cfg.state_file))as db:assert pet_rows(db,owner,'pet')[0]['digest_until']==old-7200
        assert count(135980)==before-1
        stage='feed'
        before=count(710113)
        assert(await peer.query(0x2f5,struct.pack('>QBB',item(710113)['uid'],0,0))).payload[:4]==bytes(4)
        assert count(710113)==before-1
        report['checks'].append('Exchanged135980 reduces the owned adult pet digestion deadline by native7200 seconds; exchanged710113 is consumed through original pet feeding')
        stage='fatigue'
        with closing(sqlite3.connect(cfg.state_file))as db,db:
            db.execute('UPDATE normal_fatigue_state SET current=1000 WHERE owner=?',(owner,))
        pot=item(710096);assert(await peer.query(0x196,struct.pack('>QBBBIi',pot['uid'],0,0,0,0,0))).payload[:4]==bytes(4)
        with closing(sqlite3.connect(cfg.state_file))as db:assert db.execute('SELECT current FROM normal_fatigue_state WHERE owner=?',(owner,)).fetchone()[0]==2440
        assert count(710096)==0
        report['checks'].append('Exchanged710096 is usable through original196/197 and restores its pinned native ordinary-fatigue amount')
        stage='sockets'
        from els_server.domain.normal_equipment import definitions
        from els_server.domain.sage_sockets import capacity,distribution,draw
        from els_server.domain.acquisition_policy import can_acquire
        from els_server.game_data import client_data
        selected={}
        for t in definitions():
            kind=client_data().item(t)['item_type']
            if kind not in(1,2)or kind in selected or not can_acquire(t):continue
            try:capacity(t)
            except ValueError:continue
            with closing(sqlite3.connect(cfg.state_file))as db,db:selected[kind]=grant_items(db,[dict(template=t,metadata=definitions()[t]['metadata'],group=1,quantity=1)],owner)[0]
            if len(selected)==2:break
        assert len(selected)==2
        from els_server.domain.highest_magic_stone import catalog as highest
        from collections import Counter
        for kind,target in selected.items():
            profile=distribution(target,109956);total=sum(r['weight']for r in profile);counts=Counter(draw(target,roll,109956)for roll in range(total))
            groups=highest()['categories']['weapon'if kind==1 else'armor'];assert len({sum(counts[o]for o in g['options'])for g in groups})==1
            assert all(len({counts[o]for o in g['options']})==1 for g in groups)
            for stone in(109955,109956):
                material=item(stone);request=struct.pack('>QIiQBBI',target['uid'],1,0,material['uid'],0,0,6)+bytes(24)
                before=count(stone);answer=await peer.query(0x1c4,request);assert answer.payload[:4]==bytes(4)
                with closing(sqlite3.connect(cfg.state_file))as db:pending=json.loads(db.execute('SELECT candidate_json FROM equipment_socket_pending WHERE owner=?AND item_uid=?',(owner,target['uid'])).fetchone()[0])
                answer=await peer.query(0x8b1,struct.pack('>QIiQ',target['uid'],1,0,pending[0]));assert answer.payload[:4]==bytes(4)
                cold=next(i for i in items()if i['uid']==target['uid']);assert cold['option_groups']['0'][0]==pending[0]and count(stone)==before-1
        report['checks'].append('Exact exhaustive highest-stone RNG domain has twelve equal categories/equal native tiers for weapon and armor; exchanged advanced/highest stones preview/apply/cold-read through1C4 and8B1')
        stage='quick-potion'
        from els_server.storage.quick_slots import save as save_quick,empty
        from els_server.domain.quick_bindings import item_binding
        from els_server.storage.consumables import use
        bindings=empty();bindings[0]=item_binding(710008);save_quick(cfg.state_file,struct.pack('>i',1)+__import__('els_server.storage.quick_slots',fromlist=['encode']).encode(bindings),owner)
        before=count(710008);answer=use(cfg.state_file,owner,struct.pack('>HBBB',0,0,0,0),'owned-exchanged-vitality-use',account_id=account,allow_apples=True)
        assert answer[0].payload[:4]==bytes(4)and count(710008)==before-1 and any(e.kind==0x115 for e in answer)
        saved=facts();answer=use(cfg.state_file,owner,struct.pack('>HBBB',0,0,0,0),'owned-exchanged-vitality-use',account_id=account,allow_apples=True);assert facts()==saved and not any(e.kind==0x115 for e in answer)
        report['checks'].append('Exchanged710008 uses the shared shortcut consumable writer; native effect emitted once and receipt replay does not reapply')
        assert not errors;report.update(ok=True,errors=errors)
    except BaseException:report.update(stage=stage,error=traceback.format_exc(),errors=errors)
    finally:
        for peer in peers:
            try:await peer.close()
            except Exception as error:report.setdefault('close_errors',[]).append(type(error).__name__)
        if server is not None:await server.close()
        if app is not None:app.close()
        target=K/('trainer-TLS-'+str(time.time_ns())+'.json');target.write_text(json.dumps(report,indent=2)+'\n','utf8');print(json.dumps(dict(ok=report['ok'],checks=report['checks'],stage=report.get('stage'),report=str(target),error=report.get('error'))))
    if not report['ok']:raise SystemExit(1)
asyncio.run(main())
