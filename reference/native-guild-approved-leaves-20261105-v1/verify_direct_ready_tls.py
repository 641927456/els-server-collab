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
            identities=[app.registry.create(name) for name in ('guildwiremaster','guildwireguest')]
            uids=[]
            for index,a in enumerate(identities):
                uid=Characters(cfg.state_file,a['id']).create('Wire'+str(index),1,'owned-'+str(index))['uid']
                uids.append(uid)
                with closing(sqlite3.connect(cfg.state_file))as db,db:
                    db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,))
                    db.execute('UPDATE reward_balances SET ed=6000000 WHERE uid=?',(uid,))
                LocalState(cfg.state_file,uid).save(20001,0,0,(1.,2.,3.))
            async def connect(index,*,firstmap=False):
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
                        (0x225,0x226,struct.pack('>iB',20001,0)),(0x227,0x228,struct.pack('>fffBH',1.,2.,3.,0,0))):
                    if firstmap and kind in(0x225,0x227):continue
                    await p.send(kind,body);ack=await p.until(reply)
                    if kind in (0x225,0x227):assert ack.payload[:4]==bytes(4),(kind,ack.payload.hex())
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
            stage='native-direct504-without225'
            baseline='--entry-baseline'in sys.argv
            report['baseline']=baseline
            report['direct_entry_cases']=[]
            def assets(index):
                with closing(sqlite3.connect(cfg.state_file))as db:
                    return(dict(items=load_items(db,uids[index]),
                        balances=db.execute('SELECT ed,experience FROM reward_balances WHERE uid=?',(uids[index],)).fetchone(),
                        location=db.execute('SELECT town,board,progress,x,y,z FROM location WHERE uid=?',(uids[index],)).fetchone()))
            for index,peer,firstmap in((1,guest,False),(0,master,True)):
                if firstmap:
                    await peer.close();peers.remove(peer)
                    async with asyncio.timeout(5):
                        while identities[index]['id']in app.playing:await asyncio.sleep(.01)
                    peer=await connect(index,firstmap=True)
                    assert 0x225 not in app.playing[identities[index]['id']].completed
                own=app.playing[identities[index]['id']]
                before=assets(index)
                assert(await peer.query(0x4fb,struct.pack('>IfffI',0,0.,0.,0.,25000),0x4fc)).payload[:4]==bytes(4)
                assert own.phase=='guild_agit_admitted'
                assert(await peer.query(0x508,b'',0x509)).payload[:4]!=bytes(4)
                answer=await peer.query(0x504,struct.pack('>fffBH',0.,0.,0.,0,0),0x505)
                admitted=answer.payload[:4]==bytes(4)
                assert admitted is not baseline,(firstmap,answer.payload.hex())
                assert own.phase==('guild_agit_admitted'if baseline else'guild_agit_ready')
                assert assets(index)==before
                if admitted:assert(await peer.query(0x508,b'',0x509)).payload[:4]==bytes(4)
                report['direct_entry_cases'].append(dict(first_map_login=firstmap,
                    direct_4FB_504_without_225=True,ready=admitted,saved_town_and_assets_unchanged=True,
                    bank_denied_before_504=True,bank_allowed_after_504=admitted))
            report['steps'].append('Actual4FB followed directly by504 in Town entry and first-map login: source ownership and membership retained; bank denied before504, allowed after505; saved town and assets unchanged')
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
            report['loaded_sources']={n:dict(path=str(m.__file__),sha256=hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest())
                for n,m in list(sys.modules.items())if n.startswith('els_server.')and getattr(m,'__file__',None)
                and ('guild'in n or n.endswith(('local_session','session_dispatch','application')))}
    target=OUT/('direct-ready-baseline.json'if '--entry-baseline'in sys.argv else'direct-ready-fixed.json')
    if target.exists():target=OUT/('tls-wiring-'+str(__import__('time').time_ns())+'.json')
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps({k:v for k,v in report.items()if k!='loaded_sources'},ensure_ascii=False))
    return report['ok']


if __name__=='__main__':
    raise SystemExit(0 if asyncio.run(main())else 1)
