"""Actual owned guild creation and native F1 transitions through App/TLS."""
from qa_environment import F,R,B
from contextlib import closing
import asyncio,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
from unittest.mock import patch
sys.path.insert(0,str(F.parent/'notebook-spa-clear-closure-v1/delivery-qa'))
from achievement_protocol_client import connect
from create_friends_certificate import create
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage import achievements as state,achievement_history as history
from els_server.domain import guild_banner_flow as banner
from els_server.domain.achievement_catalog import catalog,points
from els_server.domain.town_travel import catalog as towns
from els_server.protocol.social_messages import wstring
from els_server.protocol import achievement_messages as wire
from els_server.game_data import client_data

async def run():
    report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,natural_acquisition=False,
        explicit_protocol_toggle_requests=True,client_cooldown_presentation_tested=False)
    app=server=None;peers=[];errors=[]
    with tempfile.TemporaryDirectory(prefix='owned-banner-counter-',dir=F)as directory:
        private=__import__('pathlib').Path(directory);create(private,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=6,state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',
            tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
        try:
            app=Application(cfg);await app.start();a=app.registry.create('ownedbannerone');b=app.registry.create('ownedbannerother')
            uid=Characters(cfg.state_file,a['id']).create('OwnBannerA',1,'owned-banner-a')['uid']
            other=Characters(cfg.state_file,b['id']).create('OwnBannerB',2,'owned-banner-b')['uid']
            alt=Characters(cfg.state_file,a['id']).create('OwnBannerAlt',1,'owned-banner-alt')['uid']
            for owner in(uid,other,alt):LocalState(cfg.state_file,owner).save(20001,0,0,towns()['towns']['20001']['xyz'])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('UPDATE characters SET level=99');db.execute('UPDATE reward_balances SET ed=6000000,experience=?',(client_data().thresholds[98],))
                grant_items(db,[dict(template=110845,metadata=0,group=4,quantity=1)],uid)
                license=next(r['uid']for r in load_items(db,uid)if r['template']==110845)
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            def identity(owner,name,account):return dict(uid=owner,character_name=name,town=20001,bridge=dict(host='127.0.0.1',port=port,name=account['name'],token=account['token'],certificate_sha256=pin))
            def saved(account=a['id'],owner=uid):
                with closing(sqlite3.connect(cfg.state_file))as db:return dict(count=history.counts(db,account,{59}).get((59,0),0),achievement=state.snapshot(db,account,owner))
            async def toggle(peer,value,ok=True):
                reply=await peer.query(0x7e0,bytes([value]));assert(reply.payload==bytes(4))is ok,reply.payload.hex()
                return reply
            p=await connect(identity(uid,'OwnBannerA',a),peers);foreign=await connect(identity(other,'OwnBannerB',b),peers)
            await toggle(p,1,False);assert saved()['count']==0
            reply=await p.query(0x276,struct.pack('>Q',license)+wstring('BA'+str(uid))+wstring('Owned banner fixture'));assert reply.payload[:4]==bytes(4)
            await toggle(foreign,1,False);await toggle(p,0);assert saved()['count']==0
            await toggle(p,1);assert saved()['count']==1
            await toggle(p,1);await toggle(p,1);assert saved()['count']==1
            await toggle(p,0);before=saved();actor=app.playing[a['id']];assert not actor.guild_banner['active']
            original=banner.encode_event
            def reject(event):
                if event.kind==0x7e2:raise ValueError('Owned banner late encoding failure')
                return original(event)
            with patch.object(banner,'encode_event',reject):await toggle(p,1,False)
            assert saved()==before and not actor.guild_banner['active']
            original_save=state._save
            def reject_commit(db,account,owner,kind,*args):
                original_save(db,account,owner,kind,*args)
                if kind=='guild-banner':raise ValueError('Owned banner source failure after INSERT')
            with patch.object(state,'_save',reject_commit):await toggle(p,1,False)
            assert saved()==before and not actor.guild_banner['active']
            targets=[(key,c['parameters']['m_iCount'])for key,d in catalog().items()for c in d['conditions']if c['type']==59]
            assert sorted(n for key,n in targets)==[10,100,500]
            for number in range(2,11):
                start=len(p.received);await toggle(p,1);assert saved()['count']==number
                if number<10:await toggle(p,0)
            row=saved();fresh=[r for r in row['achievement']['completed']if r['id']==next(key for key,n in targets if n==10)]
            assert len(fresh)==1
            expected=wire.completion(fresh,points(row['achievement']['completed']),[],False).payload
            assert any(e.kind==0x6c0 and e.payload==expected for e in p.received[start:])
            # Direct225 to another town is correctly refused. Use the
            # original admitted guild-hall entry and return to the saved town.
            for kind,body,answer in((0x4fb,struct.pack('>IfffI',0,0.,0.,0.,25000),0x4fc),
                    (0x225,struct.pack('>iB',25000,0),0x226),
                    (0x504,struct.pack('>fffBH',0.,0.,0.,0,0),0x505)):
                reply=await p.query(kind,body,answer);assert reply.payload[:4]==bytes(4),(hex(kind),reply.payload.hex())
            assert actor.guild_banner is None and actor.phase=='guild_agit_ready'
            await toggle(p,1);await toggle(p,1);assert saved()['count']==11
            reply=await p.query(0x4fe);assert reply.payload[:4]==bytes(4)
            for kind,body in((0x225,struct.pack('>iB',20001,0)),
                    (0x227,struct.pack('>fffBH',*towns()['towns']['20001']['xyz'],0,0))):
                reply=await p.query(kind,body);assert reply.payload[:4]==bytes(4),(hex(kind),reply.payload.hex())
            await toggle(p,1);await toggle(p,1);assert saved()['count']==12
            # Same saved town, fresh native actor: the room membership
            # departure, rather than a different map ID, clears visibility.
            reply=await p.query(0x225,struct.pack('>iB',20001,0));assert reply.payload[:4]==bytes(4),reply.payload.hex()
            reply=await p.query(0x227,struct.pack('>fffBH',*towns()['towns']['20001']['xyz'],0,0));assert reply.payload[:4]==bytes(4),reply.payload.hex()
            assert actor.guild_banner is None
            await toggle(p,1);await toggle(p,1);assert saved()['count']==13
            before=saved();await p.query(0x6be);await p.query(0x6be);assert saved()==before
            old=actor;await p.close();peers.remove(p)
            async with asyncio.timeout(10):
                while app.playing.get(a['id'])is old:await asyncio.sleep(.02)
            p=await connect(identity(alt,'OwnBannerAlt',a),peers);await p.query(0x6be)
            assert saved(a['id'],alt)['achievement']['completed']==before['achievement']['completed']
            assert saved(a['id'],alt)['achievement']['watched']==[]
            await toggle(p,1,False);assert saved()['count']==13 and saved(b['id'],other)['count']==0
            assert not errors,errors
            report.update(ok=True,actual_summons=13,withdrawals_do_not_count=True,repeated_true_does_not_count=True,
                source_after_insert_rollback=True,late_encoding_rollback=True,immediate_first_threshold=True,
                actual_guild_agit_arrival=True,same_town_actor_reentry=True,same_map_return_actor_reset=True,cold_account_sharing=True,foreign_account_excluded=True,
                completed=[r['id']for r in before['achievement']['completed']],native_thresholds=targets,
                owned_level_ED_license_fixtures=True,new_tables=0,new_indexes=0)
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for peer in reversed(peers):
                try:await peer.close()
                except BaseException:report.setdefault('close_errors',[]).append(traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report.update(errors=errors,owned_directory_removed=not private.exists(),source_sha256={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(F/'source-v1').rglob('*.py')})
    (F/('counter-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));return report['ok']

if __name__=='__main__':raise SystemExit(not asyncio.run(run()))
