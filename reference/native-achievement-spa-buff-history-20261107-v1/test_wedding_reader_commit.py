"""Actual App/TLS mutual acceptance, ceremony consent, rollback and peer notices."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from qa_environment import F,R,B
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import patch
import asyncio,hashlib,json,sqlite3,ssl,struct,tempfile,time,traceback
sys.path.insert(0,str(F.parent/'guild-post-v1'))
from achievement_qa_client import connect
from create_friends_certificate import create
import els_server.domain
if '--candidate-wedding'in sys.argv:els_server.domain.__path__.insert(0,str(F/'review-candidates/els_server/domain'))
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage import achievement_history as history,achievements as state
from els_server.protocol import relationship_messages as rel,wedding_messages as wedding,achievement_messages as achievement
from els_server.protocol.social_messages import wstring
from els_server.domain import wedding_rooms
from els_server.domain.achievement_catalog import points
from els_server.domain.town_travel import catalog


async def main():
    report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,
        fixtures='Three owned actors, alternative character, two couple rings, one wedding ring and explicit future ceremony clock',
        natural_acquisition=False,checks=[])
    app=server=None;peers=[];errors=[]
    with tempfile.TemporaryDirectory(prefix='owned-relationship-history-',dir=F)as folder:
        root=Path(folder);create(root,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,
            state_file=root/'game.sqlite3',accounts_file=root/'accounts.sqlite3',
            tls_cert=root/'server-cert.pem',tls_key=root/'server-key.pem',log_dir=root/'logs')
        try:
            app=Application(cfg);await app.start();values=[]
            for index,letter in enumerate('ABC'):
                auth=app.registry.create('ownedrelhistory'+letter.lower())
                name='RelHist'+letter
                uid=Characters(cfg.state_file,auth['id']).create(name,index+1,'owned-rel-character-'+letter)['uid']
                LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
                values.append(dict(uid=uid,account_id=auth['id'],character_name=name,auth=auth))
            uid=[v['uid']for v in values];aid=[v['account_id']for v in values]
            alt=Characters(cfg.state_file,aid[0]).create('RelHistAlt',4,'owned-rel-alt')['uid']
            LocalState(cfg.state_file,alt).save(20001,0,0,catalog()['towns']['20001']['xyz'])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                grant_items(db,[dict(template=269710,metadata=0,group=4,quantity=2),
                    dict(template=277142,metadata=0,group=4,quantity=1)],uid[0])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('CREATE TABLE owned_wedding_probe(value INTEGER)');db.execute('INSERT INTO owned_wedding_probe VALUES(0)')
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))
                if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start()
            pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            for v in values:
                auth=v.pop('auth');v['bridge']=dict(host='127.0.0.1',port=port,name=auth['name'],token=auth['token'],certificate_sha256=pin)
                await connect(v,peers)
            groom,bride,guest=peers
            def read(sql,args=()):
                with closing(sqlite3.connect(cfg.state_file))as db:return db.execute(sql,args).fetchall()
            def snapshot(index):
                with closing(sqlite3.connect(cfg.state_file))as db:return state.snapshot(db,aid[index],uid[index])
            def count(index,kind):
                with closing(sqlite3.connect(cfg.state_file))as db:return history.counts(db,aid[index],{kind}).get((kind,0),0)
            def rings():return sum(r[0]for r in read('SELECT count FROM inventory_items WHERE owner=?AND template=269710',(uid[0],)))
            async def success(p,kind,body=b'',reply=None):
                answer=await p.query(kind,body,reply)
                assert answer.payload[:4]==bytes(4),(hex(kind),answer.payload[:20].hex())
                return answer
            def answer_body(answer):
                return (struct.pack('>bQ',answer,uid[0])+wstring(values[0]['character_name'])+
                    struct.pack('>QBH',0,0,0)+struct.pack('>Q',uid[1])+wstring(values[1]['character_name'])+
                    bytes(1)+rel.descriptor(values[1]['character_name']))
            async def propose():
                await success(groom,0x3fb,rel.descriptor(values[1]['character_name']))
                await bride.until(0x3fd)
            await propose();await success(bride,0x3fe,answer_body(3))
            await groom.until(0x3ff);await groom.query(0x48d,reply=0x48f)
            assert rings()==2 and count(0,18)==count(1,18)==0
            assert snapshot(0)['completed']==snapshot(1)['completed']==[]
            await propose();await success(bride,0x3fe,answer_body(0))
            await groom.until(0x3ff);await groom.query(0x48d,reply=0x48f)
            assert rings()==1 and count(0,18)==count(1,18)==1 and count(2,18)==0
            for index,p in enumerate((groom,bride)):
                saved=snapshot(index)
                expected=achievement.completion(saved['completed'],points(saved['completed']),[],False).payload
                assert any(e.kind==0x6c0 and e.payload==expected for e in p.received)
            rejected=await bride.query(0x3fe,answer_body(0));assert rejected.payload[:4]!=bytes(4)
            assert count(0,18)==count(1,18)==1 and rings()==1
            await success(groom,0x6c1,struct.pack('>i',109))
            report['checks'].append('Normal3FB/3FE refusal preserves ring and zero count; mutual acceptance consumes one ring, completes109 and immediately notifies both accounts; repeated answer adds nothing')

            now=int(time.time());ends=(now//3600+1)*3600+86340
            ring=read('SELECT uid FROM inventory_items WHERE owner=?AND template=277142',(uid[0],))[0][0]
            raw=(struct.pack('>bbQQQB',5,4,ends,uid[1],ring,0)+wstring('Owned history ceremony')+
                 wstring('')+struct.pack('>bIQ',13,1,uid[2]))
            await success(groom,0x887,raw)
            assert count(0,19)==count(1,19)==count(2,19)==0
            for p,owner in zip((groom,bride,guest),uid):
                ids=[r[0]for r in read('SELECT mail_id FROM native_relationship_mail WHERE reservation=1 AND recipient_uid=?ORDER BY mail_id',(owner,))]
                claim=struct.pack('>I',len(ids))+b''.join(struct.pack('>Q',v)for v in ids)+bytes(6)
                await success(p,0x1d4,claim)
            tickets={owner:read('SELECT uid FROM inventory_items WHERE owner=?AND template IN(277151,277152)',(owner,))[0][0]for owner in uid}
            def joining(role,owner):return struct.pack('>bQiB',role,tickets[owner],1,0)+wstring('')
            actor_type=type(app.playing[aid[0]].account);original_getter=actor_type.get_inventory_snapshot;writes=[]
            def writer_getter(account):
                if account.uid in uid:
                    try:
                        with closing(sqlite3.connect(cfg.state_file,timeout=1))as probe,probe:
                            probe.execute('BEGIN IMMEDIATE');probe.execute('UPDATE owned_wedding_probe SET value=value+1');probe.commit();writes.append(account.uid)
                    except sqlite3.Error as error:
                        report.setdefault('probe_errors',[]).append(dict(uid=account.uid,code=getattr(error,'sqlite_errorcode',None),error=repr(error)))
                        raise
                return original_getter(account)
            opened=SimpleNamespace(time=lambda:ends-86340,monotonic=time.monotonic)
            with patch.object(wedding_rooms,'time',opened):
                for p,owner,role in((groom,uid[0],2),(bride,uid[1],2),(guest,uid[2],1)):
                    with patch.object(actor_type,'get_inventory_snapshot',writer_getter):
                        await success(p,0x88b,joining(role,owner),0x415)
                room=app.world.weddings.room(app.playing[aid[0]]);assert len(room.members)==3
                with patch.object(actor_type,'get_inventory_snapshot',writer_getter):await success(guest,0x417,bytes(4))
                assert len(room.members)==2
                await success(guest,0x225,struct.pack('>iB',20001,0))
                await success(guest,0x227,struct.pack('>fffBH',*catalog()['towns']['20001']['xyz'],0,0))
                with patch.object(actor_type,'get_inventory_snapshot',writer_getter):await success(guest,0x88b,joining(1,uid[2]),0x415)
                assert len(room.members)==3
            report['checks'].append('Actual native88B spouse/guest admission,417departure and guest reentry permit a real independent inventory-repair commit before their room reader')
            inventory=read('SELECT uid,owner,template,count FROM inventory_items ORDER BY uid')
            mail_count=read('SELECT COUNT(*)FROM native_relationship_mail')[0][0]
            def expire_room(fail=False):
                with patch.object(wedding_rooms,'time',SimpleNamespace(time=lambda:ends+60,monotonic=time.monotonic)),patch.object(actor_type,'get_inventory_snapshot',writer_getter):
                    if fail:
                        from els_server.protocol import dungeon_messages
                        with patch.object(dungeon_messages,'return_user_sync',side_effect=ValueError('Owned late wedding deadline encoder')):
                            return app.world.weddings.periodic(app.playing[aid[0]])
                    return app.world.weddings.periodic(app.playing[aid[0]])
            try:await app.call(expire_room,True)
            except ValueError as error:assert str(error)=='Owned late wedding deadline encoder'
            else:raise AssertionError('Failed deadline encoder unexpectedly succeeded')
            assert len(room.members)==3 and read('SELECT finished_at FROM native_wedding_bookings')==[(None,)]
            assert read('SELECT uid,owner,template,count FROM inventory_items ORDER BY uid')==inventory
            assert read('SELECT COUNT(*)FROM native_relationship_mail')[0][0]==mail_count
            await app.call(expire_room)
            for p in(groom,bride,guest):
                await p.until(0x418)
                await success(p,0x225,struct.pack('>iB',20001,0))
                await success(p,0x227,struct.pack('>fffBH',*catalog()['towns']['20001']['xyz'],0,0))
            assert not app.world.weddings.rooms and not app.world.weddings.by_session
            assert read('SELECT reservation,mode,at FROM native_wedding_ceremonies')==[(1,'deadline',ends+60)]
            assert read('SELECT uid,owner,template,count FROM inventory_items ORDER BY uid')==inventory
            assert read('SELECT COUNT(*)FROM native_relationship_mail')[0][0]==mail_count
            assert count(0,19)==count(1,19)==count(2,19)==0
            await app.call(expire_room)
            assert read('SELECT reservation,mode,at FROM native_wedding_ceremonies')==[(1,'deadline',ends+60)]
            assert read('SELECT value FROM owned_wedding_probe')[0][0]==len(writes)and len(writes)>=9
            assert not errors and not report.get('probe_errors'),errors
            report.update(ok=True,independent_inventory_commits=len(writes),explicit_future_deadline_fixture=True,
                checks=[*report['checks'],'Original deadline worker: late return encoding rolls back marriage and retains all three members; successful expiry returns spouses and guest, adds one deadline marriage, no ceremony counts, gifts or ticket debit; replay remains stable'])
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for p in reversed(peers):
                try:await p.close()
                except BaseException:report.setdefault('close_errors',[]).append(traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report.update(errors=errors,owned_directory_removed=not root.exists(),
        source_sha256={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(F/'source-v1').rglob('*.py')})
    (F/('wedding-reader-'+str(time.time_ns())+'.json')).write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
    print(json.dumps(report,ensure_ascii=False));return report['ok']


if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
