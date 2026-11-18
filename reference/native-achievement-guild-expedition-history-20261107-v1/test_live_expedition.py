"""Owned App/TLS signup: real qualification, atomic failure and immediate notice."""
from qa_environment import F,R,B
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import asyncio,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
sys.path.insert(0,str(F.parent/'relationship-history-v1/delivery-qa'))
from achievement_protocol_client import connect
from test_sources import native_signup
from create_friends_certificate import create
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items
from els_server.storage import achievements as state,achievement_history as history,guild_system_state as system
from els_server.domain import guild_expedition as expedition
from els_server.domain.achievement_catalog import points
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain.town_travel import catalog
from els_server.game_data import client_data
from els_server.protocol import achievement_messages as wire
from els_server.protocol.local_messages import wstring


async def run():
    report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,
        historical_signup_fixture=99,level_ED_license_guild_progress_fixture=True,
        natural_acquisition=False,clock_patched=False,checks=[])
    errors=[];peers=[];app=server=None
    with tempfile.TemporaryDirectory(prefix='owned-live-expedition-',dir=F)as folder:
        private=Path(folder);create(private,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,
            state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',
            tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
        try:
            app=Application(cfg);await app.start()
            owners=[app.registry.create('ownedexphist'+v)for v in('a','b','c')]
            names=['ExpHist'+v for v in('A','B','C')]
            uid=[Characters(cfg.state_file,o['id']).create(n,i+1,'owned-exp-'+str(i))['uid']for i,(o,n)in enumerate(zip(owners,names))]
            alt=Characters(cfg.state_file,owners[1]['id']).create('ExpHistAlt',4,'owned-exp-alt')['uid']
            for value in[*uid,alt]:LocalState(cfg.state_file,value).save(20001,0,0,catalog()['towns']['20001']['xyz'])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET level=99')
                db.execute('UPDATE reward_balances SET ed=6000000,experience=?',(client_data().thresholds[98],))
                license=grant_items(db,[dict(template=110845,metadata=VERIFIED_TEMPLATES[110845],group=TEMPLATE_BAG_GROUPS[110845],quantity=1)],uid[0])[0]
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            identities=[]
            for o,value,name in zip(owners,uid,names):
                identity=dict(uid=value,character_name=name,bridge=dict(host='127.0.0.1',port=port,name=o['name'],token=o['token'],certificate_sha256=pin))
                identities.append(identity);await connect(identity,peers)
            master,member,observer=peers
            async def request(p,kind,body=b'',success=True,reply=None):
                answer=await p.query(kind,body,reply)
                assert(answer.payload[:4]==bytes(4))==success,(hex(kind),answer.payload.hex())
                return answer
            def completed(index,value=None):
                with closing(sqlite3.connect(cfg.state_file))as db:return state.snapshot(db,owners[index]['id'],uid[index]if value is None else value)
            def counts(index=1):
                with closing(sqlite3.connect(cfg.state_file))as db:return history.counts(db,owners[index]['id'],{57,58})
            def guild_facts():
                with closing(sqlite3.connect(cfg.state_file))as db:
                    names=[r[0]for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE 'native_guild_%' OR name LIKE '%quest%') ORDER BY name")]
                    return {name:list(db.execute('SELECT * FROM "'+name+'" ORDER BY rowid'))for name in names}
            await request(master,0x276,struct.pack('>Q',license['uid'])+wstring('ExpProof')+wstring('Owned fixture'))
            with closing(sqlite3.connect(cfg.state_file))as db:guild=db.execute('SELECT guild_id FROM native_guild_members WHERE owner=?',(uid[0],)).fetchone()[0]
            await request(master,0x285,wstring(names[1])+struct.pack('>Q',uid[1]));await member.until(0x287)
            await request(member,0x288,struct.pack('>i',guild)+wstring(names[0])+bytes(4))
            actor=Characters(cfg.state_file,owners[1]['id']).get(uid[1]);now=int(time.time())
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');saved=system.read(db,guild);exp=expedition._new(now);exp['stage']=12
                for number in range(1,12):expedition._stage(exp,number,now).update(hp=0,cleared=now-1)
                expedition._stage(exp,12,now);saved['expedition']=exp;system.write(db,guild,saved)
                for turn in range(99):
                    stamp=now-(100-turn)*86400;event,_=native_signup(actor,7,stamp)
                    system.record(db,'owned-history:'+str(turn),'owned-fixture',guild,uid[1],0xabc,
                        dict(events=[(event.kind,event.payload.hex())]),stamp)
            await member.query(0x6be)
            ids={r['id']for r in completed(1)['completed']}
            assert ids&set(range(344,350))=={347,348}and counts()=={(57,0):7,(58,0):99}
            await request(member,0x6c1,struct.pack('>i',347))
            signup=struct.pack('>bIQf',12,0x47505731,uid[1],1000.)
            await request(member,0xabc,signup,False)
            for kind,body,reply in((0x4fb,struct.pack('>IfffI',0,0.,0.,0.,25000),0x4fc),
                (0x225,struct.pack('>iB',25000,0),0x226),(0x504,struct.pack('>fffBH',0.,0.,0.,0,0),0x505)):
                await request(member,kind,body,reply=reply)
            await request(member,0xabc,signup,False) # Actual new-member grade and24h still apply.
            await request(master,0x28c,struct.pack('>QB',uid[1],5))
            await request(member,0xabc,signup,False) # Grade now valid; member still too recent.
            # Retain a coherent owned membership AND original join receipt.
            # This explicit24h history fixture is not elapsed natural play.
            old=app.playing[owners[1]['id']];await member.close();peers.remove(member)
            async with asyncio.timeout(10):
                while app.playing.get(owners[1]['id'])is old:await asyncio.sleep(.02)
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('UPDATE native_guild_actions SET created_at=?WHERE operation=(SELECT source_operation FROM native_guild_members WHERE owner=?)',(now-86401,uid[1]))
                db.execute('UPDATE native_guild_members SET joined_at=?WHERE owner=?',(now-86401,uid[1]))
            member=await connect(identities[1],peers)
            for kind,body,reply in((0x4fb,struct.pack('>IfffI',0,0.,0.,0.,25000),0x4fc),
                (0x225,struct.pack('>iB',25000,0),0x226),(0x504,struct.pack('>fffBH',0.,0.,0.,0,0),0x505)):
                await request(member,kind,body,reply=reply)
            await request(member,0xabc,struct.pack('>b',12),False)
            await request(member,0xabc,struct.pack('>bIQf',12,0x47505731,uid[0],1000.),False)
            assert counts()=={(57,0):7,(58,0):99}
            report['checks'].append('Normal create/invite/accept and GuildAgit arrival; town, new-member grade,24h, missing CP and foreign CP rejections add no signup')
            before=guild_facts();original=expedition.snapshot
            def fail_snapshot(saved,stamp,kind=0xabb,**kw):
                if saved is not None and kind==0xabd:raise ValueError('Owned late signup encoding failure')
                return original(saved,stamp,kind,**kw)
            with patch.object(expedition,'snapshot',fail_snapshot):await request(member,0xabc,signup,False)
            assert guild_facts()==before and counts()=={(57,0):7,(58,0):99}
            report['checks'].append('Injected late ABD encoding failure rolls back participation, honor, quests and original operation journal together')
            start=len(member.received);await request(member,0xabc,signup)
            assert counts()=={(57,0):12,(58,0):100}
            current=completed(1);fresh=[r for r in current['completed']if r['id']in(344,345,346,349)]
            assert len(fresh)==4 and current['watched']==[347]
            expected=wire.completion(fresh,points(current['completed']),[347],False).payload
            assert any(e.kind==0x6c0 and e.payload==expected for e in member.received[start:])
            assert not any(counts(0).values())and not any(counts(2).values())
            with closing(sqlite3.connect(cfg.state_file))as db:
                exp=system.read(db,guild)['expedition'];p=exp['stages']['12']['participants'][str(uid[1])]
                assert p['combat']==1000 and p['until']-p['joined']==72000 and not exp['stages']['12']['cleared']
            before=guild_facts();await request(member,0xabc,signup,False)
            assert guild_facts()==before and counts()=={(57,0):12,(58,0):100}
            await member.query(0x6be);await member.query(0x6be);assert current==completed(1)
            report['checks'].append('One valid stage12 signup immediately completes344/345/346/349 without a clear; native CP is frozen; repeated active signup and ordinary queries add nothing; other accounts uncredited')
            old=app.playing[owners[1]['id']];await member.close();peers.remove(member)
            async with asyncio.timeout(10):
                while app.playing.get(owners[1]['id'])is old:await asyncio.sleep(.02)
            alternate=await connect(dict(identities[1],uid=alt,character_name='ExpHistAlt'),peers);await alternate.query(0x6be)
            alternate_state=completed(1,alt)
            assert {r['id']for r in alternate_state['completed']}&set(range(344,350))==set(range(344,350))
            assert alternate_state['watched']==[]and completed(1)['watched']==[347]
            assert not errors,errors
            report.update(ok=True,checks=[*report['checks'],'Cold alternative-character login restores six account achievements and independent character display'],
                new_tables=0,new_indexes=0,signup_counts=100,maximum_participated_stage=12)
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for p in reversed(peers):
                try:await p.close()
                except BaseException:report.setdefault('close_errors',[]).append(traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report['errors']=errors
    report['source_sha256']={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(F/'source-v1').rglob('*.py')}
    (F/('live-expedition-'+str(time.time_ns())+'.json')).write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
    print(json.dumps(report,ensure_ascii=False));return report['ok']


if __name__=='__main__':raise SystemExit(not asyncio.run(run()))
