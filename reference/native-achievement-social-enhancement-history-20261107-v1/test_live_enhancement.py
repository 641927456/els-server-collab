"""Actual ordinary and smith settlements: both outcomes count, rejects do not."""
from qa_environment import F,R,B
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import asyncio,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
sys.path.insert(0,str(F.parent/'relationship-history-v1/delivery-qa'))
from achievement_protocol_client import connect
from create_friends_certificate import create
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.inventory_actions import _commit
from els_server.storage.equipment_enhancement import replace as enhancement
from els_server.storage.enhancement_progress import replace as gauge
from els_server.storage import achievement_history as history,achievements as state,profession_state
from els_server.storage import paid_enhancement as paid,blacksmith_enhancement as smith
from els_server.protocol.profession_messages import ProfessionState
from els_server.protocol import achievement_messages as wire
from els_server.domain.blacksmith_enhancement_rules import materials
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain.achievement_catalog import points
from els_server.domain.town_travel import catalog
from els_server.game_data import client_data


async def run():
    report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,
        natural_acquisition=False,fixtures='Owned99retained attempts, full enhancement gauge, level/ED/profession/materials and explicit isolated RNG draws',checks=[])
    app=server=None;peers=[];errors=[]
    with tempfile.TemporaryDirectory(prefix='owned-live-enhancement-count-',dir=F)as folder:
        private=Path(folder);create(private,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,
            state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',
            tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
        try:
            app=Application(cfg);await app.start();owner=app.registry.create('ownedattemptcount');other=app.registry.create('ownedattemptother')
            names=('AttOrdinary','AttSmith','AttAlt');uid=[Characters(cfg.state_file,owner['id']).create(n,i+1,'own-attempt-'+str(i))['uid']for i,n in enumerate(names)]
            foreign=Characters(cfg.state_file,other['id']).create('AttOther',4,'own-attempt-other')['uid']
            for u in[*uid,foreign]:LocalState(cfg.state_file,u).save(20001,0,0,catalog()['towns']['20001']['xyz'])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET level=99')
                db.execute('UPDATE reward_balances SET ed=100000000,experience=?',(client_data().thresholds[98],))
                profession_state.replace(db,uid[1],owner['id'],0,ProfessionState(2,1,0,{},0,400))
                def grant(u,t,n=1):return grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=n)],u)[0]
                success_gear=grant(uid[0],60100);fail_gear=grant(uid[0],60100);smith_gear=grant(uid[1],60100)
                enhancement(db,uid[0],success_gear['uid'],0,9);gauge(db,uid[0],dict(success_gear,enhancement=9),180,0)
                for u,item in((uid[0],fail_gear),(uid[1],smith_gear)):enhancement(db,u,item['uid'],0,7)
                grant(uid[0],163284,2);grant(uid[1],163284,2)
                template,matrix=materials();grant(uid[1],template,2*matrix[8][1])
                _commit(db,'own-attempt-schema','fixture',uid[0],0x555,[],[],[])
                for n in range(99):
                    snapshot=json.dumps([dict(fail_gear,enhancement=7)])
                    db.execute('INSERT INTO inventory_action_receipts VALUES(?,?,?,?,?,?,?)',('own-retained-attempt:'+str(n),'retained-fixture',uid[0],0x5ff,'[]',snapshot,snapshot))
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            def identity(i,auth=owner,u=None,n=None):return dict(uid=uid[i]if u is None else u,character_name=names[i]if n is None else n,
                bridge=dict(host='127.0.0.1',port=port,name=auth['name'],token=auth['token'],certificate_sha256=pin))
            def count(account=owner):
                with closing(sqlite3.connect(cfg.state_file))as db:return history.counts(db,account['id'],{30}).get((30,0),0)
            def current(u):
                with closing(sqlite3.connect(cfg.state_file))as db:return state.snapshot(db,owner['id'],u)
            def economy(u):
                with closing(sqlite3.connect(cfg.state_file))as db:
                    db.execute('BEGIN');return(load_items(db,u),db.execute('SELECT ed FROM reward_balances WHERE uid=?',(u,)).fetchone(),count())
            def body(item,mode=0,profession=False):return struct.pack('>QiiBBBBiB',item['uid'],mode,0,int(profession),0,1,0,0,0)
            async def request(p,data,success=True):
                reply=await p.query(0x5ff,data)
                assert(reply.payload[:4]==bytes(4))==success,reply.payload[:32].hex()
                return reply
            async def close_actor(p):
                old=app.playing[owner['id']];await p.close();peers.remove(p)
                async with asyncio.timeout(10):
                    while app.playing.get(owner['id'])is old:await asyncio.sleep(.02)
            a=await connect(identity(0),peers);assert count()==99
            start=len(a.received);success_body=body(success_gear,4);reply=await request(a,success_body)
            assert struct.unpack_from('>i',reply.payload,12)[0]==1 and count()==100
            snapshot=current(uid[0]);fresh=[r for r in snapshot['completed']if r['id']==165];assert len(fresh)==1
            expected=wire.completion(fresh,points(snapshot['completed']),[],False).payload
            assert any(e.kind==0x6c0 and e.payload==expected for e in a.received[start:])
            with closing(sqlite3.connect(cfg.state_file))as db:
                operation=db.execute('SELECT operation_id FROM inventory_action_receipts WHERE owner=?AND kind=?AND request_hash<>?ORDER BY rowid DESC LIMIT 1',(uid[0],0x5ff,'retained-fixture')).fetchone()[0]
            before=economy(uid[0]);paid.enhance(cfg.state_file,uid[0],success_body,operation,account_id=owner['id'],authorize=lambda:True)
            assert economy(uid[0])==before and count()==100
            with patch.object(paid.enhance,'__defaults__',(lambda denominator:1000,)):
                reply=await request(a,body(fail_gear));assert struct.unpack_from('>i',reply.payload,12)[0]==3
                assert count()==101
                before=economy(uid[0])
                with patch.object(paid,'acknowledgement',side_effect=ValueError('Owned late ordinary encoder failure')):await request(a,body(fail_gear),False)
                assert economy(uid[0])==before and count()==101
            await request(a,body(dict(uid=2**62)),False);assert count()==101
            report['checks'].append('Actual full-gauge ordinary success crosses100 and immediately completes165; same committed operation replay is stable; actual no-change failure counts once, late encoding fault and foreign UID refusal add none')
            await close_actor(a);b=await connect(identity(1),peers)
            with patch.object(smith.enhance,'__defaults__',(lambda denominator:10000,)):
                reply=await request(b,body(smith_gear,profession=True));assert struct.unpack_from('>i',reply.payload,12)[0]==3
            assert count()==102
            with patch.object(smith.enhance,'__defaults__',(lambda denominator:0,)):
                reply=await request(b,body(smith_gear,profession=True));assert struct.unpack_from('>i',reply.payload,12)[0]==1
            assert count()==103 and count(other)==0
            report['checks'].append('Actual blacksmith failure and success each count once with the original profession/material/ED transactions; same-account roles share103 and foreign account remains zero')
            before=current(uid[1]);await b.query(0x6be);await b.query(0x6be);assert current(uid[1])==before
            await close_actor(b);alternate=await connect(identity(2),peers);await alternate.query(0x6be)
            assert 165 in{r['id']for r in current(uid[2])['completed']}and current(uid[2])['watched']==[]
            assert not errors,errors
            report.update(ok=True,attempts=103,actual_ordinary_success_and_failure=True,actual_smith_success_and_failure=True,
                actual_operation_replay_stable=True,isolated_RNG_draws=[1000,10000,0],production_probability_policy_changed=False)
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for p in reversed(peers):
                try:await p.close()
                except BaseException:report.setdefault('close_errors',[]).append(traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report['errors']=errors
    report['source_sha256']={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(F/'source-v1').rglob('*.py')}
    (F/('live-enhancement-'+str(time.time_ns())+'.json')).write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
    print(json.dumps(report,ensure_ascii=False));return report['ok']


if __name__=='__main__':raise SystemExit(not asyncio.run(run()))
