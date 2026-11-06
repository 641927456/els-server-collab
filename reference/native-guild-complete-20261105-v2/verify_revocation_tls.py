"""Current release through isolated authenticated TLS and native guild requests."""
from contextlib import closing
from pathlib import Path
import asyncio
import hashlib
import json
import sqlite3
import ssl
import struct
import sys
import tempfile
import traceback

import overlay
ROOT = Path('G:/els')
OUT = Path(__file__).resolve().parent
BASE = overlay.BASE
point = {'release':json.loads((OUT/'source.json').read_bytes())['release']+' + guild candidate'}
sys.dont_write_bytecode = True
sys.path[:0] = [str(BASE), str(BASE/'vendor'), str(ROOT/'tools/pylibs'), str(ROOT)]

from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.friends_bridge import Bridge, BridgeConfig
from els_server.protocol.protocol_codec import BOOTSTRAP_KEYS, Event, encode_event, encode_frame, decode_frame, decode_event, read_welcome
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items, load_items
from els_server.storage.guild_membership_state import cold as guild_cold
from tools.create_friends_certificate import create


def ws(text):
    raw = text.encode('utf-16le')
    return struct.pack('>I',len(raw))+raw


class Peer:
    async def send(self, kind, payload=b''):
        self.writer.write(encode_frame(encode_event(Event(0x202,kind=kind,payload=payload,performers=(0,))),
            self.keys,spi=self.spi,sequence=self.outgoing))
        self.outgoing += 1
        await self.writer.drain()

    async def until(self, kind):
        async with asyncio.timeout(12):
            for _ in range(240):
                header = await self.reader.readexactly(8)
                wire = header+await self.reader.readexactly(struct.unpack_from('<I',header)[0]-8)
                event = decode_event(decode_frame(wire,self.keys,expected_sequence=self.incoming).plaintext)
                self.incoming += 1
                self.received.append(event)
                if event.kind == kind:return event
        raise AssertionError('Missing response '+hex(kind))

    async def query(self, kind, payload, reply):
        await self.send(kind,payload)
        event = await self.until(reply)
        await self.send(0x48d)
        await self.until(0x48f)
        return event

    async def close(self):
        self.writer.close()
        try:await self.writer.wait_closed()
        except ssl.SSLError as error:
            if error.reason!='APPLICATION_DATA_AFTER_CLOSE_NOTIFY':raise
        await self.bridge.close()


async def main():
    report = dict(release=point['release'],ok=False,steps=[],ui_queries=[],natural_GUI=False,
        production_mutations=False,fixture='Owned isolated level99, ED6000000 and ordinary material; session phases only advanced by original requests')
    peers=[];stage='start';app=server=None
    with tempfile.TemporaryDirectory(prefix='owned-tls-',dir=OUT) as temporary:
        private=Path(temporary)
        cert=create(private,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=private/'game.sqlite3',
            accounts_file=private/'accounts.sqlite3',tls_cert=private/'server-cert.pem',
            tls_key=private/'server-key.pem',log_dir=private/'logs')
        try:
            app=Application(cfg);await app.start()
            logs=[]
            server=GameServer(cfg,app,lambda event,**kw:logs.append(dict(event=event,**kw)))
            _,port=await server.start()
            identities=[app.registry.create(name) for name in ('guildwiremaster','guildwireguest','guildwireluciel')]
            uids=[]
            for index,a in enumerate(identities):
                uid=Characters(cfg.state_file,a['id']).create('Wire'+str(index),10 if index==2 else 1,'owned-'+str(index))['uid']
                uids.append(uid)
                with closing(sqlite3.connect(cfg.state_file))as db,db:
                    db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,))
                    db.execute('UPDATE reward_balances SET ed=6000000 WHERE uid=?',(uid,))
                LocalState(cfg.state_file,uid).save(20001,0,0,(1.,2.,3.))
            async def connect(index,*,agit=False):
                a=identities[index];p=Peer()
                p.bridge=Bridge(BridgeConfig('127.0.0.1',port,a['name'],a['token'],cert))
                p.reader,p.writer=await p.bridge.remote()
                p.keys=BOOTSTRAP_KEYS;p.incoming=1;p.received=[]
                welcome=await p.until(0x1)
                p.spi,p.keys=read_welcome(welcome);p.outgoing=1
                peers.append(p)
                for kind,reply in ((0x1a,0x1b),(0x1e,0x19c),(0x35,0x36),(0x1ef,0x1f0),(0x39,0x3a),(0x485,0x488)):
                    await p.send(kind);await p.until(reply)
                for kind,reply,body in ((0x490,0x491,b''),(0x28,0x29,struct.pack('>Q',uids[index])),
                        (0x6e9,0x6ea,b''),(0x5bf,0x5c0,bytes(8)),(0x32,0x33,b''),
                        *(((0x4fb,0x4fc,struct.pack('>IfffI',0,0.,0.,0.,25000)),(0x225,0x226,struct.pack('>iB',25000,0)),(0x504,0x505,struct.pack('>fffBH',0.,0.,0.,0,0)))if agit else((0x225,0x226,struct.pack('>iB',20001,0)),(0x227,0x228,struct.pack('>fffBH',1.,2.,3.,0,0))))):
                    await p.send(kind,body);ack=await p.until(reply)
                    if kind in (0x225,0x227,0x4fb,0x504):assert ack.payload[:4]==bytes(4),(kind,ack.payload.hex())
                await p.query(0x48d,b'',0x48f)
                return p
            stage='normal-login'
            master=await connect(0);guest=await connect(1)
            s=app.playing[identities[0]['id']]
            report['normal_town_state']=dict(phase=s.phase,active_map=s.active_map,pending_map=s.pending_map,
                completed=sorted(s.completed),world_member=app.world.members.get(s))
            async def inspect_ui_queries(label):
                for kind,reply in ((0x27b,0x27c),(0xacd,0xace),(0x84f,0x850)):
                    start=len(master.received)
                    await master.send(kind)
                    await master.query(0x48d,b'',0x48f)
                    received=[e for e in master.received[start:] if e.kind!=0x48f]
                    report['ui_queries'].append(dict(state=label,request=hex(kind),expected=hex(reply),
                        expected_received=any(e.kind==reply for e in received),response_kinds=[hex(e.kind)for e in received]))
            stage='guildless-menu-queries'
            await inspect_ui_queries('no_membership')
            stage='license-purchase'
            ack=await master.query(0xea,struct.pack('>BHIiii',0,0,1,110845,1,10018),0xeb)
            assert ack.payload[:4]==bytes(4),ack.payload.hex()
            license=next(i for i in s.account.get_inventory_snapshot()['items']if i['template']==110845)
            report['steps'].append('Ariel EA/EB purchase110845, ED debit and inventory')
            stage='guild-create'
            ack=await master.query(0x276,struct.pack('>Q',license['uid'])+ws('WireGuild')+ws(''),0x277)
            assert ack.payload[:4]==bytes(4),ack.payload.hex()
            saved=guild_cold(cfg.state_file,uids[0],identities[0]['id'])
            assert saved is not None
            assert any(e.kind==0x278 for e in master.received)
            report['steps'].append('276/277 plus278, actual consumed license and persisted membership')
            stage='member-menu-queries'
            await inspect_ui_queries('guild_master')
            stage='invite-accept'
            ack=await master.query(0x285,ws('Wire1')+struct.pack('>Q',uids[1]),0x286)
            assert ack.payload[:4]==bytes(4),ack.payload.hex()
            await guest.until(0x287)
            ack=await guest.query(0x288,struct.pack('>i',saved['id'])+ws('Wire0')+bytes(4),0x289)
            assert ack.payload==bytes(4)
            assert len(guild_cold(cfg.state_file,uids[1],identities[1]['id'])['members'])==2
            report['steps'].append('285/286/287 invitation and288/289/28B saved acceptance')
            stage='core-member-commands'
            # New member has no management right; the actual rejection must persist nothing.
            refused=await guest.query(0x28e,ws('forbidden'),0x28f)
            assert refused.payload[:4]!=bytes(4),refused.payload.hex()
            assert(await master.query(0x28e,ws('owned announcement'),0x28f)).payload==bytes(4)
            assert(await master.query(0x853,ws('owned joining rule'),0x854)).payload[:4]==bytes(4)
            assert(await master.query(0xac9,ws('owned login notice'),0xaca)).payload[:4]==bytes(4)
            assert(await master.query(0x84f,b'',0x850)).payload==bytes(4)+ws('owned joining rule')
            for rank in(5,4,3,2):
                a=await master.query(0x28c,struct.pack('>QB',uids[1],rank),0x28d)
                assert a.payload[:4]==bytes(4),a.payload.hex()
                assert guild_cold(cfg.state_file,uids[1],identities[1]['id'])['grade']==rank
            assert(await guest.query(0x292,struct.pack('>Q',uids[1])+ws('owned greeting'),0x293)).payload[:4]==bytes(4)
            for view in(0,1,2,3):
                a=await master.query(0x279,struct.pack('>Ib',1,view),0x27a)
                assert a.payload[:4]==bytes(4),a.payload.hex()
            assert(await guest.query(0x27d,bytes((1,))+ws('owned message'),0x27e)).payload==struct.pack('>iB',0,9)
            assert(await guest.query(0x27b,b'',0x27c)).payload==struct.pack('>iB',0,9)
            a=await guest.query(0x27f,struct.pack('>IBi',1,0,0),0x280)
            assert a.payload[:4]==bytes(4) and 'owned message'.encode('utf-16le') in a.payload,a.payload.hex()
            with closing(sqlite3.connect(cfg.state_file))as db:
                from els_server.storage.guild_system_state import read
                actual=read(db,saved['id'])
                assert actual['member_details'][str(uids[1])]['message']=='owned greeting'
                assert actual['rules']=='owned joining rule'
                assert actual['announcement']=='owned login notice'
            report['steps'].append('Actual native UI queries, management rejection, all six grades, announcement, joining rule, member greeting, roster and guild board persisted')
            for p in (master,guest):
                stage='agit-entry'
                ack=await p.query(0x4fb,struct.pack('>IfffI',0,0.,0.,0.,25000),0x4fc)
                assert ack.payload[:4]==bytes(4),ack.payload.hex()
                ack=await p.query(0x225,struct.pack('>iB',25000,0),0x226)
                assert ack.payload[:4]==bytes(4),ack.payload.hex()
                ack=await p.query(0x504,struct.pack('>fffBH',0.,0.,0.,0,0),0x505)
                assert ack.payload[:4]==bytes(4),ack.payload.hex()
            report['steps'].append('Both actors native4FB/4FC,225/226 and504/505 GuildAgit readiness')
            def assets():
                with closing(sqlite3.connect(cfg.state_file))as db:
                    return [(load_items(db,uid),db.execute('SELECT ed,experience FROM reward_balances WHERE uid=?',(uid,)).fetchone(),db.execute('SELECT town,board,progress,x,y,z FROM location WHERE uid=?',(uid,)).fetchone())for uid in uids]
            before=assets()
            stage='transfer-kick-in-agit'
            assert(await master.query(0x28c,struct.pack('>QB',uids[1],1),0x28d)).payload[:4]==bytes(4)
            assert guild_cold(cfg.state_file,uids[0],identities[0]['id'])['grade']==2
            assert guild_cold(cfg.state_file,uids[1],identities[1]['id'])['master_uid']==uids[1]
            previous=len(guest.received)
            assert(await guest.query(0x290,struct.pack('>QB',uids[0],1),0x291)).payload[:4]==bytes(4)
            assert guild_cold(cfg.state_file,uids[0],identities[0]['id'])is None
            for _ in range(80):
                kicked_note=await master.until(0x284)
                if kicked_note.payload[0]==7:break
            else:raise AssertionError('Native own kick notification missing')
            assert not any(e.kind==0x284 and e.payload[0]==7 for e in guest.received[previous:])
            assert any(e.kind==0x500 for e in guest.received[previous:])
            assert(await master.query(0x508,b'',0x509)).payload[:4]!=bytes(4)
            assert(await guest.query(0x294,b'',0x295)).payload[:4]!=bytes(4)
            report['steps'].append('Actual master transfer, recipient-specific kick and GuildAgit peer removal; revoked member cannot bank and can return to saved town')
            stage='agit-return'
            for p in (master,guest):
                assert(await p.query(0x4fe,b'',0x4ff)).payload==bytes(4)
                assert(await p.query(0x225,struct.pack('>iB',20001,0),0x226)).payload[:4]==bytes(4)
                assert(await p.query(0x227,struct.pack('>fffBH',1.,2.,3.,0,0),0x228)).payload[:4]==bytes(4)
            report['steps'].append('4FE/4FF and original225/227 return to normal town')
            assert assets()==before
            assert app.playing[identities[0]['id']].phase=='town_ready'
            assert app.playing[identities[1]['id']].phase=='town_ready'
            assert guild_cold(cfg.state_file,uids[0],identities[0]['id'])is None
            report['steps'].append('Kicked GuildAgit actor receives284 and remains connected; bank still refuses; actual4FE/225/227 returns to the saved town with all original assets unchanged')
            report['ok']=True
        except BaseException:
            report['failure_stage']=stage
            report['failure']=traceback.format_exc()
        finally:
            for p in reversed(peers):
                try:await p.close()
                except Exception:pass
            if server is not None:await server.close()
            if app is not None:app.close()
            report['connections_closed']=server is None or not server.connections
            report['worker_errors']=[r for r in logs if 'error'in r.get('event','')]
            if report['worker_errors']:report['ok']=False
            report['loaded_sources']={n:dict(path=str(m.__file__),sha256=hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest())
                for n,m in list(sys.modules.items())if n.startswith('els_server.')and getattr(m,'__file__',None)
                and ('guild'in n or n.endswith(('local_session','session_dispatch','application')))}
    target=OUT/'revocation-tls.json'
    if target.exists():target=OUT/('revocation-tls-'+str(__import__('time').time_ns())+'.json')
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps({k:v for k,v in report.items()if k!='loaded_sources'},ensure_ascii=False))
    return report['ok']


if __name__=='__main__':
    raise SystemExit(0 if asyncio.run(main())else 1)
