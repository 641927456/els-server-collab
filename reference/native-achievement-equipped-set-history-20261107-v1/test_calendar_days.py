"""Original App/TLS upkeep with an explicit isolated clock dependency fixture."""
from qa_environment import F,R,B
from pathlib import Path
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import patch
import asyncio,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
sys.path.insert(0,str(F/'delivery-qa'))
from achievement_protocol_client import connect
from create_friends_certificate import create
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage import achievements as state
from els_server.storage.achievement_history import record_play_day,counts
from els_server.storage.achievement_profiles import reconcile
from els_server.domain import achievement_flow as flow
from els_server.domain.achievement_catalog import points
from els_server.protocol import achievement_messages as wire
from els_server.domain.town_travel import catalog

async def main():
    report=dict(ok=False,production_database_access=False,production_clock_patch=False,isolated_flow_clock_dependency_fixture=True,natural_midnight=False,native_Game=False,checks=[])
    peers=[];errors=[];app=server=None
    with tempfile.TemporaryDirectory(prefix='owned-calendar-days-',dir=F)as folder:
        private=Path(folder);create(private,'127.0.0.1');cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
        try:
            app=Application(cfg);await app.start();values=[]
            for i,letter in enumerate('AB'):
                auth=app.registry.create('ownedcalendar'+letter.lower());name='OwnCal'+letter;uid=Characters(cfg.state_file,auth['id']).create(name,i+1,'owned-calendar-'+letter)['uid'];values.append(dict(uid=uid,account_id=auth['id'],character_name=name,town=20001,auth=auth))
            a,b=values;alt=Characters(cfg.state_file,a['account_id']).create('OwnCalAlt',1,'owned-calendar-alt')['uid']
            for uid in(a['uid'],b['uid'],alt):LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
            now=int(time.time());today=(now+28800)//86400;edge=(today+1)*86400-28800
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE')
                for n in range(1,99):record_play_day(db,a['account_id'],a['uid'],(today-n)*86400-28800+3600)
            def count(v):
                with closing(sqlite3.connect(cfg.state_file))as db:return counts(db,v['account_id'],{10}).get((10,0),0)
            def saved():
                with closing(sqlite3.connect(cfg.state_file))as db:return state.snapshot(db,a['account_id'],alt)
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            for v in values:
                auth=v.pop('auth');v['bridge']=dict(host='127.0.0.1',port=port,name=auth['name'],token=auth['token'],certificate_sha256=pin)
            p=await connect(a,peers);q=await connect(b,peers);assert count(a)==99 and count(b)==1
            old=app.playing[a['account_id']];await p.close();peers.remove(p)
            async with asyncio.timeout(10):
                while app.playing.get(a['account_id'])is old:await asyncio.sleep(.02)
            p=await connect(dict(a,uid=alt,character_name='OwnCalAlt'),peers);assert count(a)==99 and 42 not in{r['id']for r in saved()['completed']}
            with patch.object(flow,'time',SimpleNamespace(time=lambda:edge-1)):
                await p.query(0x48d,reply=0x48f);assert count(a)==99
            start=len(p.received)
            with patch.object(flow,'time',SimpleNamespace(time=lambda:edge)):
                async with asyncio.timeout(8):
                    while count(a)!=100:await asyncio.sleep(.02)
                notice=await p.until(0x6c0);current=saved();fresh=[r for r in current['completed']if r['id']==42];assert len(fresh)==1
                assert notice.payload==wire.completion(fresh,points(current['completed']),current['watched'],False).payload
                for _ in range(3):await p.query(0x48d,reply=0x48f)
                assert count(a)==100
            report['checks'].append('Actual native cold entry records only one account/date across siblings;23:59:59does not add a date, original periodic upkeep at isolated00:00:00records the100th date and emits completion42 without a new counter request')
            with patch.object(flow,'time',SimpleNamespace(time=lambda:edge+3*86400)):
                async with asyncio.timeout(8):
                    while count(a)!=101:await asyncio.sleep(.02)
                await p.query(0x48d,reply=0x48f);assert count(a)==101
            before=saved();previous=count(a);late=edge+4*86400
            try:
                with closing(sqlite3.connect(cfg.state_file))as db,db:
                    db.execute('BEGIN IMMEDIATE');record_play_day(db,a['account_id'],alt,late);reconcile(db,a['account_id'],alt,late,condition_types={10})
                    raise ValueError('Owned late calendar response failure')
            except ValueError as error:assert str(error)=='Owned late calendar response failure'
            assert count(a)==previous and saved()==before
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');record_play_day(db,a['account_id'],alt,late);record_play_day(db,a['account_id'],a['uid'],late);reconcile(db,a['account_id'],alt,late,condition_types={10})
            assert count(a)==previous+1
            assert not errors,errors
            report.update(ok=True,checks=[*report['checks'],'Jumping across three offline dates adds only the entered date; late caller failure rolls back both source and progress; retry and same-date primary/sibling replay add exactly one'])
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for peer in reversed(peers):await peer.close()
            if server is not None:await server.close()
            if app is not None:app.close()
    report['errors']=errors;report['source_sha256']={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted((F/'source-v1').rglob('*.py'))}
    p=F/('calendar-days-'+str(time.time_ns())+'.json');p.write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps(report,ensure_ascii=False));return report['ok']

if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
