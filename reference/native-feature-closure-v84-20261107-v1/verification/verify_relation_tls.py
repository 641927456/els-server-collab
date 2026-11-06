"""Real isolated App/TLS for native mentor invitations, consent and cold restore."""
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import asyncio,ctypes,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
R=Path('G:/els');W=Path(__file__).resolve().parent
B=Path('G:\\els\\analysis\\feature-closure-20261105-v1\\release-integration-v2\\full-source');C=B/'els_server'
sys.dont_write_bytecode=True
sys.path[:0]=[str(B),str(R/'tools'),str(R/'tools/pylibs'),str(R),'G:\\els\\analysis\\feature-closure-20261105-v1\\delivery-duel-v1']
_sqlite=ctypes.WinDLL('G:\\els\\analysis\\feature-closure-20261105-v1\\duel-wire-v2\\full-source\\python\\sqlite3.dll')
import els_server,els_server.domain,els_server.protocol,els_server.storage
for namespace,folder in((els_server,''),(els_server.domain,'domain'),(els_server.storage,'storage'),(els_server.protocol,'protocol')):
    namespace.__path__.insert(0,str(C/folder))
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.seal_quests import QuestState
from els_server.storage.inventory_state import grant_items
from els_server.storage import mentor_relations as storage
from els_server.domain.mentor45000 import LIMITS
from els_server.domain.character_rules import CLASSES
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain.town_travel import catalog
from els_server.protocol import mentor_messages as wire,quest_messages
from els_server.protocol.protocol_codec import encode_event
from create_friends_certificate import create
from native_peer import connect

async def main():
    report=dict(ok=False,checks=[],private_authenticated_TLS=True,native_game=False,natural_GUI=False,
        qualification_objectives_are_explicit_fixture=True,production_database_access=False,
        source_files={p.relative_to(C).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in C.rglob('*.py')})
    app=server=None;peers=[];events=[]
    with tempfile.TemporaryDirectory(prefix='owned-mentor-tls-',dir=W)as name:
        own=Path(name).resolve();assert own.parent==W.resolve()
        create(own,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=own/'game.sqlite3',
            accounts_file=own/'accounts.sqlite3',tls_cert=own/'server-cert.pem',tls_key=own/'server-key.pem',log_dir=own/'logs')
        try:
            app=Application(cfg);await app.start();values=[]
            for index,letter in enumerate('ABC'):
                identity=app.registry.create('ownedmentortls'+letter.lower())
                uid=Characters(cfg.state_file,identity['id']).create('MentorTLS'+letter,index+1,'mentor-tls-'+letter)['uid']
                LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
                values.append(dict(account_id=identity['id'],identity=identity,uid=uid,character_name='MentorTLS'+letter))
            teacher_uid=values[0]['uid'];career=next(k for k,v in CLASSES.items() if v['base_class']==1 and v['stage']==2)
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('UPDATE characters SET level=99,unit_class=?,revision=revision+1 WHERE uid=?',(career,teacher_uid))
            def teacher_guard(db):assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(teacher_uid,)).fetchone()==(values[0]['account_id'],)
            quest=QuestState(cfg.state_file,teacher_uid,account_id=values[0]['account_id'],account_source_guard=teacher_guard)
            quest.action('accept',dict(quest=45000,npc=10025),'mentor-tls-qualified',lambda r:[])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('UPDATE character_quests SET objectives=? WHERE owner=? AND quest=45000',
                    (json.dumps({str(k):v for k,v in LIMITS.items()},sort_keys=True),teacher_uid))
                grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=20)
                                for t in (701000,78150,78250)],teacher_uid)
            def claim(result):
                message=quest_messages.initialization(result['state']);encode_event(message);return [message]
            quest.action('claim',quest_messages.request(0xf4,struct.pack('>iiI5B',45000,0,0,0,0,0,0,0)),'mentor-tls-qualification-claim',claim)
            server=GameServer(cfg,app,lambda event,**kw:events.append(dict(event=event,**kw)))
            _,port=await server.start()
            for value in values:
                identity=value.pop('identity')
                value['bridge']=dict(host='127.0.0.1',port=port,name=identity['name'],token=identity['token'],
                    certificate_sha256=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest())
                await connect(value,peers)
            teacher,student,outsider=peers
            uid=[v['uid']for v in values]
            sessions=[app.playing[v['account_id']]for v in values]
            def read(sql,args=()):
                with closing(sqlite3.connect(cfg.state_file))as db:return db.execute(sql,args).fetchall()
            def mentors():
                with closing(sqlite3.connect(cfg.state_file))as db:
                    if not storage.exists(db,'native_mentor_relations'):return []
                    return db.execute('SELECT *FROM native_mentor_relations ORDER BY owner').fetchall()
            def received(peer,kind,start):return next((e for e in peer.received[start:]if e.kind==kind),None)
            async def after(peer,kind,start):return received(peer,kind,start)or await peer.until(kind)
            async def barrier(peer):await peer.send(0x48d);await peer.until(0x48f)
            async def invite():
                start=len(student.received)
                ack=await teacher.query(0x1e8,struct.pack('>Q',uid[1]))
                assert ack.payload[:4]==bytes(4),ack.payload.hex()
                incoming=await after(student,0x1ea,start)
                with closing(sqlite3.connect(cfg.state_file))as db:
                    expected=wire.public_info(storage.public_info(db,uid[0],sessions[0],is_student=False))
                assert incoming.payload==expected
            async def answer(accepted=True,reason=1964,target=None):
                starts=[len(teacher.received),len(student.received)]
                await student.send(0x1eb,struct.pack('>Q',uid[0]if target is None else target)+wire.EMPTY_ANSWER_INFO+
                    bytes((accepted,))+struct.pack('>i',reason))
                if accepted:
                    result=await after(student,0x1eb,starts[1])
                    return result,starts
                return await after(teacher,0x1eb,starts[0]),starts
            assert [struct.unpack('>i',next(e for e in reversed(p.received)if e.kind==0x717).payload)[0]for p in peers]==[0,1,1]
            await invite();rejected,_=await answer(False)
            assert rejected.payload[-5:]==b'\0'+struct.pack('>i',1964) and not mentors()
            await invite();wrong,_=await answer(target=uid[2])
            assert wrong.payload[-5]==0 and not mentors()
            report['checks'].append('Cold717 roles; original1E8/1E9/1EA; refusal and wrong-target answer never bind')
            with patch.object(wire,'answer',side_effect=ValueError('Owned late answer encoder failure')):
                failed,_=await answer()
                assert failed.payload[-5]==0 and not mentors()
            accepted,starts=await answer()
            assert accepted.payload[-5:]==b'\1'+bytes(4)
            invited=await after(teacher,0x1eb,starts[0]);assert invited.payload[-5:]==b'\1'+bytes(4)
            assert len(mentors())==2 and not app.world.mentors.pending
            baseline=read('SELECT *FROM reward_balances ORDER BY uid')
            other_ack=await outsider.query(0x1e4,struct.pack('>Q',uid[0]))
            assert struct.unpack_from('>i',other_ack.payload)[0]==1981 and len(mentors())==2
            too_early=await student.query(0x1e4,struct.pack('>Q',uid[0]))
            assert struct.unpack_from('>i',too_early.payload)[0]==1974 and len(mentors())==2
            report['checks'].append('Late native encoding rollback; both original1EB results; outsider cannot remove;48h boundary enforced on the wire')
            before=mentors();start=len(teacher.received)
            await student.close();peers.remove(student)
            deadline=time.monotonic()+5
            while app.playing.get(values[1]['account_id'])is sessions[1]:
                assert time.monotonic()<deadline;await asyncio.sleep(.01)
            await barrier(teacher)
            offline=await after(teacher,0x1e7,start)
            with closing(sqlite3.connect(cfg.state_file))as db:
                saved=storage.relation(db,uid[0]);expected=wire.partner(storage.public_info(db,uid[1],None,saved=saved)).payload
            # Older online projections can already be queued on this socket.
            # Consume the ordered stream until the actual disconnect projection.
            for _ in range(10):
                if offline.payload==expected:break
                offline=await teacher.until(0x1e7)
            assert offline.payload==expected,(offline.payload.hex(),expected.hex())
            student=await connect(values[1],peers)
            sessions[1]=app.playing[values[1]['account_id']]
            assert any(e.kind==0x1e7 and struct.unpack_from('>Q',e.payload,1)[0]==uid[0]for e in student.received)
            assert mentors()==before
            report['checks'].append('Disconnect projects offline partner; authenticated cold reconnect restores the same generation and counterpart without writes')
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('UPDATE native_mentor_relations SET formed_at=?',(int(time.time())-storage.MIN_RELATION_SECONDS,))
            start=len(teacher.received)
            removed=await student.query(0x1e4,struct.pack('>Q',uid[0]))
            assert removed.payload[:4]==bytes(4) and not mentors()
            await after(teacher,0x1e6,start)
            await invite();accepted,starts=await answer();assert accepted.payload[-5]==1
            await after(teacher,0x1eb,starts[0])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('UPDATE native_mentor_relations SET formed_at=?',(int(time.time())-storage.MIN_RELATION_SECONDS,))
                db.execute('UPDATE characters SET level=99,revision=revision+1 WHERE uid=?',(uid[1],))
            graduated=await student.query(0x1e4,struct.pack('>Q',uid[0]))
            assert graduated.payload[:4]==bytes(4) and not mentors()
            assert read('SELECT student,teacher FROM native_mentor_graduations')==[(uid[1],uid[0])]
            assert len(read('SELECT id FROM game_mail WHERE campaign LIKE ?',('mentor-graduate-%',)))==1
            assert read('SELECT *FROM reward_balances ORDER BY uid')==baseline
            report['checks'].append('Explicit48h/99 fixtures: remove and immediately rebind; graduation ends relation and issues one token letter with no ED/XP change')
            report['ok']=True
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for peer in reversed(peers):
                try:await peer.close()
                except BaseException:report.update(ok=False,cleanup_error=traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report['worker_errors']=[row for row in events if row['event']in('worker_error','notification_error','connection_task_error')]
    if report['worker_errors']:report['ok']=False
    report['owned_directory_removed']=not own.exists()
    out=W/('relation-tls-'+str(time.time_ns())+'.json')
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps(dict(ok=report['ok'],checks=report['checks'],error=report.get('error'),cleanup_error=report.get('cleanup_error'),
        worker_errors=report['worker_errors'],evidence=str(out)),ensure_ascii=False))
    return report['ok']
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
