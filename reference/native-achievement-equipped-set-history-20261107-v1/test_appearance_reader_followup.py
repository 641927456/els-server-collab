"""Read-only variant audit: real GuildAgit display and independent getter commit."""
from qa_environment_v2 import F,R,B
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import asyncio,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
import els_server.domain,els_server.storage
if '--candidate-flow'in sys.argv:
    els_server.domain.__path__.insert(0,str(F.parent/'equipment-set-history-v1/source-v1/els_server/domain'))
    els_server.storage.__path__.insert(0,str(F.parent/'equipment-set-history-v1/source-v1/els_server/storage'))
sys.path.insert(0,str(F/'delivery-qa-v2'))
from achievement_protocol_client import connect
from create_friends_certificate import create
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items
from els_server.storage import achievements as state
from els_server.protocol.social_messages import wstring
from els_server.domain.town_travel import catalog
from els_server.game_data import client_data

async def main():
    report=dict(ok=False,production_database_access=False,native_Game=False,checks=[])
    peers=[];errors=[];app=server=None;commits=[]
    with tempfile.TemporaryDirectory(prefix='owned-appearance-followup-',dir=F)as folder:
        private=Path(folder);create(private,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
        try:
            app=Application(cfg);await app.start();values=[]
            for i,letter in enumerate('AB'):
                auth=app.registry.create('ownedappearance'+letter.lower());name='OwnAppear'+letter
                uid=Characters(cfg.state_file,auth['id']).create(name,i+1,'owned-appearance-'+letter)['uid']
                values.append(dict(account_id=auth['id'],uid=uid,character_name=name,town=20001,auth=auth))
                LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET level=99');db.execute('UPDATE reward_balances SET ed=6000000,experience=?',(client_data().thresholds[98],))
                license=grant_items(db,[dict(template=110845,metadata=0,group=4,quantity=1)],values[0]['uid'])[0];state.ensure(db)
                db.execute('CREATE TABLE owned_appearance_probe(value INTEGER)');db.execute('INSERT INTO owned_appearance_probe VALUES(0)')
                for n in range(10):state._save(db,values[0]['account_id'],values[0]['uid'],'duel-invite','0'*64,'owned-appearance-request:'+str(n),dict(target=values[1]['uid'],created_at=int(time.time())-100+n))
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            for value in values:
                auth=value.pop('auth');value['bridge']=dict(host='127.0.0.1',port=port,name=auth['name'],token=auth['token'],certificate_sha256=pin);await connect(value,peers)
            a,b=peers
            async def request(peer,kind,body=b'',reply=None):
                answer=await peer.query(kind,body,reply);assert answer.payload[:4]==bytes(4),(hex(kind),answer.payload[:20].hex());return answer
            await request(a,0x276,struct.pack('>Q',license['uid'])+wstring('OwnAppear')+wstring('Owned fixture'))
            with closing(sqlite3.connect(cfg.state_file))as db:guild=db.execute('SELECT guild_id FROM native_guild_members WHERE owner=?',(values[0]['uid'],)).fetchone()[0]
            await request(a,0x285,wstring(values[1]['character_name'])+struct.pack('>Q',values[1]['uid']));await b.until(0x287)
            await request(b,0x288,struct.pack('>i',guild)+wstring(values[0]['character_name'])+bytes(4))
            actor_type=type(app.playing[values[0]['account_id']].account);original=actor_type.get_inventory_snapshot
            def getter(account):
                if account.uid==values[0]['uid']:
                    with closing(sqlite3.connect(cfg.state_file,timeout=.6))as db:
                        db.execute('BEGIN IMMEDIATE');db.execute('UPDATE owned_appearance_probe SET value=value+1');db.commit();commits.append(account.uid)
                return original(account)
            for peer in peers:
                for kind,body,reply in((0x4fb,struct.pack('>IfffI',0,0.,0.,0.,25000),0x4fc),(0x225,struct.pack('>iB',25000,0),0x226),(0x504,struct.pack('>fffBH',0.,0.,0.,0,0),0x505)):
                    if '--probe-admission'in sys.argv and kind==0x504:
                        with patch.object(actor_type,'get_inventory_snapshot',getter):await request(peer,kind,body,reply)
                    else:await request(peer,kind,body,reply)
            with patch.object(actor_type,'get_inventory_snapshot',getter):await request(a,0x6c1,struct.pack('>i',160))
            assert commits and not errors,(commits,errors)
            report.update(ok=True,checks=['Actual GuildAgit achievement display permits independent inventory getter commit and returns normal watch ACK'])
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for peer in reversed(peers):await peer.close()
            if server is not None:await server.close()
            if app is not None:app.close()
    from els_server.domain import achievement_flow,guild_agit_flow
    report.update(errors=errors,independent_commits=len(commits),source_sha256=hashlib.sha256(Path(achievement_flow.__file__).read_bytes()).hexdigest(),guild_source_sha256=hashlib.sha256(Path(guild_agit_flow.__file__).read_bytes()).hexdigest(),candidate_flow='--candidate-flow'in sys.argv,probe_admission='--probe-admission'in sys.argv)
    target=F/('appearance-reader-followup-'+str(time.time_ns())+'.json');target.write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps(report,ensure_ascii=False));return report['ok']

if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
