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
    previous=K/'trainer-TLS-1793978933819593700.json';prior=json.loads(previous.read_bytes())
    assert not prior['ok']and prior['stage']=='sockets'and len(prior['checks'])==5
    report=dict(ok=False,actual_authenticated_TLS=True,native_Game=False,natural_GUI=False,production_database_access=False,
                reused_checks=prior['checks'],reused_report_sha256=hashlib.sha256(previous.read_bytes()).hexdigest(),checks=[])
    private=K/'trainer-TLS-v1/1793978925268258100'
    cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'retry-logs')
    app=server=None;peers=[];errors=[];stage='retained-own-fixture'
    try:
        app=Application(cfg);await app.start()
        owner=1001
        with closing(sqlite3.connect(cfg.state_file))as db:
            assert db.execute('SELECT name FROM characters WHERE uid=?',(owner,)).fetchone()==('TrainerOwn0',)
            account=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()[0]
        def items():
            with closing(sqlite3.connect(cfg.state_file))as db:return load_items(db,owner)
        def item(t):return next(i for i in items()if i['template']==t)
        def count(t):return sum(i['count']for i in items()if i['template']==t)
        def facts():
            with closing(sqlite3.connect(cfg.state_file))as db:return {t:db.execute('SELECT *FROM '+t+' ORDER BY 1').fetchall()for t in('inventory_items','reward_balances','pet_progression')}
        from els_server.storage.sage_sockets import socket
        from els_server.storage.npc_trade import InsufficientED
        target=next(i for i in items()if i['group']==1);material=item(109955)
        request=struct.pack('>QIiQBBI',target['uid'],1,0,material['uid'],0,0,6)+bytes(24)
        before=facts()
        try:socket(cfg.state_file,owner,request,'own-reproduce-unfunded-fixture',account_id=account,session_id='own-preflight')
        except InsufficientED:pass
        else:raise AssertionError('Retained failed fixture must lack merchant ED')
        assert facts()==before
        with closing(sqlite3.connect(cfg.state_file))as db,db:db.execute('UPDATE reward_balances SET ed=1000000 WHERE uid=?',(owner,))
        report['checks'].append('Retained fixture reproduces InsufficientED without mutation; only owned QA balance funded for the remaining socket checks')
        with closing(app.registry.connect())as db,db:
            identity=db.execute('SELECT name FROM accounts WHERE id=?',(account,)).fetchone()
            assert identity==('ownedtrainer0',)
            credential=app.registry.issue_session(db,account,identity[0])
        server=GameServer(cfg,app,lambda event,**kw:errors.append(event)if event in('protocol_error','worker_error','notification_error','connection_task_error')else None);_,port=await server.start()
        actor=dict(uid=owner,bridge=dict(host='127.0.0.1',port=port,name=credential['name'],token=credential['token'],certificate_sha256=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()))
        await connect(actor,peers);peer=peers[0];session=app.playing[account]
        stage='sockets'
        from els_server.domain.normal_equipment import definitions
        from els_server.domain.sage_sockets import capacity,distribution,draw
        from els_server.domain.acquisition_policy import can_acquire
        from els_server.game_data import client_data
        selected={client_data().item(i['template'])['item_type']:i for i in items()if i['group']==1}
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
        from els_server.storage.quick_slots import save_request as save_quick,empty
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
        target=K/('trainer-consumption-reuse-'+str(time.time_ns())+'.json');target.write_text(json.dumps(report,indent=2)+'\n','utf8');print(json.dumps(dict(ok=report['ok'],checks=report['checks'],stage=report.get('stage'),report=str(target),error=report.get('error'))))
    if not report['ok']:raise SystemExit(1)
asyncio.run(main())
