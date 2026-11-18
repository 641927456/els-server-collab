"""Actual isolated App/TLS: anniversary delivery, eleven-item preview and uses."""
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from datetime import datetime,time as daytime,timedelta
import asyncio,ctypes,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback

R=Path('G:/els');W=Path(__file__).resolve().parent;B=W/'test-source-v1'
sys.dont_write_bytecode=True
sys.path[:0]=[str(B),str(R/'tools'),str(R/'tools/pylibs'),str(R),str(W.parent/'delivery-duel-v1')]
_sqlite=ctypes.WinDLL(str(W.parent/'duel-wire-v2/full-source/python/sqlite3.dll'))
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items
from els_server.storage import relationships,fixed_cubes,normal_fatigue
from els_server.protocol import relationship_messages as rel
from els_server.protocol.social_messages import wstring
from els_server.domain.item_expiration import CLIENT_ZONE
from els_server.domain.town_travel import catalog
from create_friends_certificate import create
from native_peer import connect


async def main():
    report=dict(ok=False,checks=[],private_authenticated_TLS=True,native_Game=False,natural_GUI=False,
                qualification_objectives_are_explicit_fixture=True,production_database_access=False)
    app=server=None;peers=[];events=[]
    with tempfile.TemporaryDirectory(prefix='owned-relationship-tls-',dir=W)as name:
        own=Path(name).resolve();assert own.parent==W.resolve();create(own,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=own/'game.sqlite3',accounts_file=own/'accounts.sqlite3',
                         tls_cert=own/'server-cert.pem',tls_key=own/'server-key.pem',log_dir=own/'logs')
        try:
            app=Application(cfg);await app.start();values=[]
            for index,letter in enumerate('AB'):
                identity=app.registry.create('ownedrelation'+letter.lower())
                uid=Characters(cfg.state_file,identity['id']).create('RelationTLS'+letter,index+1,'owned-character-'+letter)['uid']
                LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
                values.append(dict(account_id=identity['id'],identity=identity,uid=uid,character_name='RelationTLS'+letter))
            uid=[v['uid']for v in values];aid=[v['account_id']for v in values]
            now=int(time.time());day=datetime.fromtimestamp(now,CLIENT_ZONE).date()-timedelta(days=14)
            base=int(datetime.combine(day,daytime(hour=12),CLIENT_ZONE).timestamp())
            def guard(db):assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid[0],)).fetchone()==(aid[0],)
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                grant_items(db,[dict(template=269710,metadata=0,group=4,quantity=1)],uid[0])
                db.execute('UPDATE reward_balances SET ed=500 WHERE uid=?',(uid[0],))
                relationships.propose(db,uid[0],aid[0],uid[1],aid[1],'owned-groom','owned-bride',rel.descriptor('RelationTLSB'),
                                      'owned-proposal',guard=guard,encode=lambda *args:[],now=base)
                body=struct.pack('>bQ',0,uid[0])+wstring('RelationTLSA')+struct.pack('>QBH',0,0,0)+struct.pack('>Q',uid[1])+wstring('RelationTLSB')+bytes(1)+rel.descriptor('RelationTLSB')
                relationships.answer(db,uid[1],aid[1],uid[0],aid[0],'owned-bride','owned-groom',body,'owned-acceptance',guard=guard,encode=lambda *args:[],now=base)
                if not normal_fatigue._exists(db,'normal_fatigue_state'):db.execute(normal_fatigue.STATE_SQL)
                # Explicit owned input: low fatigue, not a claimed dungeon run.
                db.execute('INSERT INTO normal_fatigue_state VALUES(?,?,?,?,?)',(uid[0],normal_fatigue._day(now),1000,1,now))
            server=GameServer(cfg,app,lambda event,**kw:events.append(dict(event=event,**kw)));_,port=await server.start()
            for v in values:
                identity=v.pop('identity')
                v['bridge']=dict(host='127.0.0.1',port=port,name=identity['name'],token=identity['token'],
                    certificate_sha256=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest())
                await connect(v,peers)
            groom,bride=peers
            def read(sql,args=()):
                with closing(sqlite3.connect(cfg.state_file))as db:return db.execute(sql,args).fetchall()
            await groom.query(0xc09)
            letters=read('SELECT mail_id FROM native_relationship_mail WHERE recipient_uid=? ORDER BY mail_id',(uid[0],))
            assert len(letters)==2
            result=await groom.query(0x1cc,struct.pack('>BiBB',2,1,0,0));assert struct.unpack_from('>iiI',result.payload)==(0,2,2)
            assert result.payload[-7:]==struct.pack('>iBBB',1,2,0,0)
            wrong=await bride.query(0x1d2,struct.pack('>Q',letters[0][0]));assert wrong.payload[:4]!=bytes(4)
            body=struct.pack('>IQQI2B',2,letters[0][0],letters[1][0],0,0,0)
            claimed=await groom.query(0x1d4,body);assert claimed.payload[:4]==bytes(4)
            assert read('SELECT count FROM inventory_items WHERE owner=?AND template=160762',(uid[0],))==[(2,)]
            report['checks'].append('Authenticated join/periodic issues two real due letters; original1CC relationship folder lists2; foreign account read refuses; original1D4 claims2 real cube attachments')
            await groom.query(0x80d,struct.pack('>i',1))
            bought=await groom.query(0x80f,struct.pack('>IIHIH',2,1200277141,1,1200277142,1))
            assert bought.payload[:4]==bytes(4)and read('SELECT ed FROM reward_balances WHERE uid=?',(uid[0],))==[(400,)]
            assert read('SELECT template,count FROM inventory_items WHERE owner=?AND template IN(277141,277142)ORDER BY template',(uid[0],))==[(277141,1),(277142,1)]
            preview=await groom.query(0x559,struct.pack('>iIBB',160762,0,0,0))
            assert preview.payload[:8]==struct.pack('>ii',0,160762)and struct.unpack_from('>I',preview.payload,17)[0]==11
            box=read('SELECT uid FROM inventory_items WHERE owner=?AND template=160762',(uid[0],))[0][0]
            raw=struct.pack('>QBBBIi',box,0,0,0,0,0);original=fixed_cubes.open_cube
            for roll,template in((0,77200),(1,111087)):
                def forced(*args,**kwargs):return original(*args,**kwargs,randbelow=lambda bound:roll)
                with patch.object(fixed_cubes,'open_cube',side_effect=forced):answer=await groom.query(0x196,raw)
                assert answer.payload[:4]==bytes(4),(roll,answer.payload.hex())
                assert read('SELECT count FROM inventory_items WHERE owner=?AND template=?',(uid[0],template))==[(1,)]
            report['checks'].append('Actual80D/80F buys both50ED rings for100ED; original559 lists11 choices; two real196 requests use current session authority and deliver fatigue potion and3-revival box')
            for template,field,expected in((77200,8,2440),(111087,4,3)):
                item=read('SELECT uid FROM inventory_items WHERE owner=?AND template=?',(uid[0],template))[0][0]
                used=await groom.query(0x196,struct.pack('>QBBBIi',item,0,0,0,0,0))
                assert used.payload[:4]==bytes(4)and struct.unpack_from('>i',used.payload,field)[0]==expected,(template,used.payload.hex())
                assert not read('SELECT uid FROM inventory_items WHERE uid=?',(item,))
            assert read('SELECT current FROM normal_fatigue_state WHERE owner=?',(uid[0],))==[(2440,)]
            assert read('SELECT count FROM known_resurrection_stones WHERE owner=?',(uid[0],))==[(3,)]
            report['checks'].append('Earned potion restores exactly30% of4800 through native197 fatigue field; earned revival box credits exactly3 through existing197 revival field; both source items disappear')
            session=app.playing[aid[0]]
            await groom.close();peers.remove(groom)
            deadline=time.monotonic()+5
            while app.playing.get(aid[0])is session:
                assert time.monotonic()<deadline;await asyncio.sleep(.01)
            groom=await connect(values[0],peers)
            assert len(read('SELECT mail_id FROM native_relationship_mail WHERE recipient_uid=?',(uid[0],)))==2
            assert not read('SELECT uid FROM inventory_items WHERE owner=?AND template IN(160762,77200,111087)',(uid[0],))
            assert read('SELECT current FROM normal_fatigue_state WHERE owner=?',(uid[0],))==[(2440,)]
            assert read('SELECT count FROM known_resurrection_stones WHERE owner=?',(uid[0],))==[(3,)]
            report['checks'].append('Real authenticated cold reconnect retains ring inventory,2440 fatigue,3 revivals and two original mail receipts without reminting consumed rewards')
            report['ok']=True
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for peer in reversed(peers):
                try:await peer.close()
                except BaseException:report.update(ok=False,cleanup_error=traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report['worker_errors']=[e for e in events if e['event']in('worker_error','notification_error','connection_task_error')]
    if report['worker_errors']:report['ok']=False
    report['owned_directory_removed']=not own.exists()
    report['candidate_files']={p.relative_to(W/'candidate').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(W/'candidate').rglob('*')if p.is_file()}
    out=W/('relationship-tls-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps(dict(ok=report['ok'],checks=report['checks'],error=report.get('error'),worker_errors=report['worker_errors'],evidence=str(out)),ensure_ascii=False))
    return report['ok']
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
