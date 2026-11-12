"""Account Unit restore and peer publication through current original readers."""
from pathlib import Path
from contextlib import closing
import asyncio,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_live_profiles import W,Application,ServerConfig,GameServer,Characters,LocalState,create,catalog,connect,state
from els_server.domain.achievement_catalog import achievement
from els_server.protocol import local_messages,social_messages
from els_server.protocol.protocol_codec import Event
from role_native_replay import Replay,IMAGE_SHA
from unicorn.x86_const import UC_X86_REG_RIP


class UnitReplay(Replay):
    def invalid(self,uc,access,address,size,value,user):
        self.last_fault=dict(rip=hex(uc.reg_read(UC_X86_REG_RIP)),address=hex(address),size=size)
        return False


def stream(replay,raw):
    data=replay.alloc(len(raw));replay.write(data,raw);buffer=replay.alloc(48)
    replay.write(buffer+8,struct.pack('<QQQ',data,data+len(raw),data+len(raw)))
    reader=replay.alloc(40);replay.call(0x3b6d140,reader);replay.call(0x3b6d1c0,reader,buffer,0)
    return reader,buffer


def vector(replay,p):
    begin,end,_=struct.unpack('<QQQ',replay.read(p,24));assert (end-begin)%4==0
    return list(struct.unpack('<'+'i'*((end-begin)//4),replay.read(begin,end-begin)))if begin!=end else []


def status(replay,dto):
    return dict(points=vector(replay,dto),watched=vector(replay,dto+24),state_flag=bool(replay.read(dto+48,1)[0]))


def read_peer(replay,raw):
    reader,buffer=stream(replay,raw);dto=replay.alloc(0x20d)
    replay.call(0x2c44f70,dto)
    assert replay.call(0xda0e50,reader,dto)&255==1
    consumed=int.from_bytes(replay.read(buffer+32,4),'little')
    return status(replay,dto+0x134),consumed


async def run():
    report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,
        original_reader_replay=True,image_sha256=IMAGE_SHA,completion_fixture=True,checks=[])
    errors=[];peers=[];app=server=None
    with tempfile.TemporaryDirectory(prefix='owned-achievement-unit-',dir=W)as folder:
        private=Path(folder);create(private,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,
            state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',
            tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
        try:
            app=Application(cfg);await app.start();owner=app.registry.create('ownedachunit');foreign=app.registry.create('ownedachunitpeer')
            chars=Characters(cfg.state_file,owner['id']);other=Characters(cfg.state_file,foreign['id'])
            a=chars.create('AchUnitA',1,'owned-unit-create-A')['uid']
            b=chars.create('AchUnitB',2,'owned-unit-create-B')['uid']
            c=other.create('AchUnitC',3,'owned-unit-create-C')['uid']
            for uid in(a,b,c):LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            def identity(account,uid,name):return dict(uid=uid,character_name=name,bridge=dict(host='127.0.0.1',port=port,name=account['name'],token=account['token'],certificate_sha256=pin))
            first=await connect(identity(owner,a,'AchUnitA'),peers)
            peer=await connect(identity(foreign,c,'AchUnitC'),peers)
            for p in peers:await p.query(0x6be)
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE')
                state.record(db,owner['id'],a,[dict(achievement=19,condition=r['id'],value=1,complete=True)
                    for r in achievement(19)['conditions']],'owned-unit-completion',int(time.time()))
            expected=dict(points=[achievement(19)['points'],0,0,0],watched=[19],state_flag=False)
            answer=await first.query(0x6c1,struct.pack('>i',19),0x6c2);assert answer.payload[:4]==bytes(4)
            await peer.query(0x48d,reply=0x48f)
            replay=UnitReplay()
            added=[]
            for event in peer.received:
                if event.kind!=0x22a:continue
                count,=struct.unpack_from('>I',event.payload)
                if count!=1 or int.from_bytes(event.payload[4:12],'big')!=a:continue
                decoded,n=read_peer(replay,event.payload[4:]);added.append(decoded)
                tail=event.payload[4+n:]
                removed,=struct.unpack_from('>I',tail)
                assert tail==struct.pack('>IQ',1,a)if removed else tail==bytes(4)
            assert added[-1]==expected,added
            for row in chars.list():
                assert row['achievement_status']==dict(expected,watched=[19]if row['uid']==a else [])
            assert other.get(c)['achievement_status']==dict(points=[0,0,0,0],watched=[],state_flag=False)
            # Creating a sibling on an established account must inherit scores
            # even in the pre-commit creation DTO, while displays stay private.
            new=chars.create('AchUnitD',4,'owned-unit-create-D')
            assert new['achievement_status']==dict(expected,watched=[])
            for uid in(a,b,new['uid'],c):
                character=(chars if uid!=c else other).get(uid)
                raw=local_messages.character_unit(character=character)
                ok,consumed,dto,_,_=replay.unit(raw)
                assert ok==1 and consumed==len(raw)
                assert status(replay,dto+0x4c7)==character['achievement_status']
            live=app.playing[owner['id']]
            for _ in range(2):
                full=live.saved_user_sync();assert full.kind==0xd9
                # Original D9B170 consumes the leading complete Unit. The bag
                # tail is intentionally not treated as part of that DTO.
                ok,consumed,dto,_,_=replay.unit(full.payload)
                assert ok==1 and status(replay,dto+0x4c7)==expected
                assert consumed<len(full.payload)
            # Refresh publications use the existing town member path. Removing
            # a display must publish an empty list, retaining the same scores.
            await first.query(0x6c1,struct.pack('>i',19),0x6c2);await peer.query(0x48d,reply=0x48f)
            latest=next(e for e in reversed(peer.received)if e.kind==0x22a and e.payload[:4]==struct.pack('>I',1)and int.from_bytes(e.payload[4:12],'big')==a)
            decoded,_=read_peer(replay,latest.payload[4:]);assert decoded==dict(expected,watched=[])
            with closing(sqlite3.connect(cfg.state_file))as db:
                before=list(db.iterdump());assert state.statuses(db,owner['id'],(a,b,new['uid']))[a]==dict(expected,watched=[])
                assert before==list(db.iterdump())
            assert not errors,errors
            report.update(ok=True,checks=[
                'Ordinary6C1 publishes both display enable and disable to an authenticated peer via existing22A; originalDA0E50 reads DTO+134 exactly',
                'Common Characters roster/get and new sibling creation share account scores and preserve per-character displays; foreign account remains zero',
                'Original D9B170 reads all four generated full Unit DTOs, including account siblings and foreign account, without trailing bytes',
                'Two ordinary saved D9 refresh DTOs retain scores and displays; read-only status projection makes no SQLite changes'])
        except BaseException:
            report['error']=traceback.format_exc()
            if 'replay'in locals():report['native_fault']=getattr(replay,'last_fault',None)
        finally:
            for p in peers:
                try:await p.close()
                except Exception:report.setdefault('close_errors',[]).append(traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report['errors']=errors
    output=W/('full-unit-projection-'+str(time.time_ns())+'.json');output.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(report,ensure_ascii=False));return report['ok']


if __name__=='__main__':raise SystemExit(not asyncio.run(run()))
