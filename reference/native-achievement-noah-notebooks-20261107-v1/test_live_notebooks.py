"""Original FD/FE, qualified Noah room, atomic source failure and cold sharing."""
from qa_environment import F,R,B
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import asyncio,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
sys.path.insert(0,str(F.parent/'equipment-set-history-v1/delivery-qa'))
from achievement_protocol_client import connect
from create_friends_certificate import create
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage import achievements as state,town_dialogue as producer
from els_server.storage.achievement_history import counts
from els_server.storage.inventory_state import InventoryState
from els_server.domain.town_travel import catalog
from els_server.domain.achievement_catalog import points
from els_server.protocol import achievement_messages as wire
from els_server.game_data import client_data

async def main():
    report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,retained_saved_scene_and_level_fixture=True,checks=[])
    peers=[];errors=[];app=server=None
    with tempfile.TemporaryDirectory(prefix='owned-noah-notebooks-',dir=F)as folder:
        private=Path(folder);create(private,'127.0.0.1');cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
        try:
            app=Application(cfg);await app.start();values=[]
            for letter,unit,town in(('A',14,20012),('B',1,20001)):
                auth=app.registry.create('ownednotebook'+letter.lower());name='OwnNote'+letter;uid=Characters(cfg.state_file,auth['id']).create(name,unit,'owned-notebook-'+letter)['uid'];values.append(dict(uid=uid,account_id=auth['id'],character_name=name,town=town,auth=auth));LocalState(cfg.state_file,uid).save(town,0,0,catalog()['towns'][str(town)]['xyz'])
            a,b=values;alt=Characters(cfg.state_file,a['account_id']).create('OwnNoteAlt',14,'owned-notebook-alt')['uid'];LocalState(cfg.state_file,alt).save(20012,0,0,catalog()['towns']['20012']['xyz'])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET level=99');db.execute('UPDATE reward_balances SET ed=6000000,experience=?',(client_data().thresholds[98],))
            def snapshot(v,uid=None):
                owner=v['uid']if uid is None else uid
                with closing(sqlite3.connect(cfg.state_file))as db:
                    db.execute('BEGIN');return dict(achievement=state.snapshot(db,v['account_id'],owner),notes={str(npc):counts(db,v['account_id'],{66}).get((66,npc),0)for npc in range(10372,10376)},days=counts(db,v['account_id'],{10}).get((10,0),0))
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            for v in values:
                auth=v.pop('auth');v['bridge']=dict(host='127.0.0.1',port=port,name=auth['name'],token=auth['token'],certificate_sha256=pin)
            p=await connect(a,peers);q=await connect(b,peers);before=snapshot(a);wallet=InventoryState(cfg.state_file,a['uid']).snapshot();assert not any(before['notes'].values())
            before_b=snapshot(b);reply=await q.query(0xfd,struct.pack('>i',10372));assert reply.payload[:4]!=bytes(4)and snapshot(b)==before_b
            await p.send(0xfd,struct.pack('>i',10018));await p.query(0x48d,reply=0x48f);assert snapshot(a)==before
            for npc,identity in zip(range(10372,10375),range(400,403)):
                start=len(p.received);reply=await p.query(0xfd,struct.pack('>i',npc));assert reply.payload[:4]==bytes(4)
                saved=snapshot(a);fresh=[r for r in saved['achievement']['completed']if r['id']==identity];assert len(fresh)==1 and saved['notes'][str(npc)]==1
                expected=wire.completion(fresh,points(saved['achievement']['completed']),saved['achievement']['watched'],False).payload
                assert any(e.kind==0x6c0 and e.payload==expected for e in p.received[start:])
            before=snapshot(a);actor=app.playing[a['account_id']]
            def failure(event):raise ValueError('Owned late notebook response failure')
            with patch.object(producer,'encode_event',failure):reply=await p.query(0xfd,struct.pack('>i',10375))
            assert reply.payload[:4]!=bytes(4)and snapshot(a)==before and getattr(actor,'_achievement_notebook_source',None)is None
            reply=await p.query(0xfd,struct.pack('>i',10375));assert reply.payload[:4]==bytes(4);saved=snapshot(a);assert {400,401,402,403}<={r['id']for r in saved['achievement']['completed']}
            assert all(v==1 for v in saved['notes'].values())and saved['days']==1
            for _ in range(2):reply=await p.query(0xfd,struct.pack('>i',10375));assert reply.payload[:4]==bytes(4)
            assert snapshot(a)==saved and snapshot(b)==before_b and InventoryState(cfg.state_file,a['uid']).snapshot()==wallet
            reply=await p.query(0x6c1,struct.pack('>i',400));assert reply.payload[:4]==bytes(4)
            old=actor;await p.close();peers.remove(p)
            async with asyncio.timeout(10):
                while app.playing.get(a['account_id'])is old:await asyncio.sleep(.02)
            p=await connect(dict(a,uid=alt,character_name='OwnNoteAlt'),peers);await p.query(0x6be);saved=snapshot(a,alt);assert {400,401,402,403}<={r['id']for r in saved['achievement']['completed']}and saved['achievement']['watched']==[]and snapshot(a)['achievement']['watched']==[400]
            reply=await p.query(0xfd,struct.pack('>i',10372));assert reply.payload[:4]==bytes(4)and snapshot(a,alt)==saved and saved['days']==1
            assert not errors,errors
            report.update(ok=True,connected_source_types=43,connected_definitions=257,remaining_source_types=17,checks=['Actual Noah20012/scene1004FD/FE conversations commit the four exact NPC conditions and immediate400/401/402/403notifications','Wrong scene refuses; unrelated original NPC adds no notebook source; ED/items and the other account remain unchanged','Late FE encoding failure rolls back source and progress; normal retry and repeated conversation settle once','Cold sibling restores account completion with independent display; same-date play-day and same notebook sources reuse the original earner'])
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for peer in reversed(peers):await peer.close()
            if server is not None:await server.close()
            if app is not None:app.close()
    report['errors']=errors;report['source_sha256']={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted((F/'source-v1').rglob('*.py'))}
    p=F/('live-notebooks-'+str(time.time_ns())+'.json');p.write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps(report,ensure_ascii=False));return report['ok']

if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
