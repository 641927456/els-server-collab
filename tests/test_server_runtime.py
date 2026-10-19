"""Real TCP regression for the service lifecycle, framing and connection bounds."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import struct
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from els_server.config import ServerConfig
from els_server.application import Application
from els_server.transport import GameServer
from els_server.protocol.protocol_codec import (BOOTSTRAP_KEYS,Event,encode_event,encode_frame,
                                              decode_event,decode_frame,read_welcome)
from els_server.storage.lifecycle import SaveLease,prepare_database,checkpoint_database
from els_server.observability import EventLog


async def read_wire(reader):
    header=await asyncio.wait_for(reader.readexactly(8),2)
    return header+await asyncio.wait_for(reader.readexactly(struct.unpack_from('<I',header)[0]-8),2)


async def run(directory):
    config=ServerConfig(port=0,profile='bootstrap',state_file=directory/'test.sqlite3',
                        log_dir=directory/'logs',max_connections=2,
                        idle_timeout=2,frame_timeout=.2,write_timeout=1,shutdown_timeout=1)
    events=[]
    def log(event,**values):events.append(dict(event=event,**values))
    app=Application(config);server=GameServer(config,app,log)
    await app.start();host,port=await server.start()
    writers=[]
    async def connect():
        r,w=await asyncio.open_connection(host,port);writers.append(w)
        spi,keys=read_welcome(decode_event(decode_frame(await read_wire(r),BOOTSTRAP_KEYS).plaintext))
        return r,w,spi,keys
    async def disconnect(w):
        w.close();await w.wait_closed()
        for _ in range(100):
            if not server.connections:break
            await asyncio.sleep(.005)
    try:
        # Cumulative connections must not prevent the 33rd and later reconnects.
        for _ in range(40):
            r,w,spi,keys=await connect();await disconnect(w)
        assert server.metrics['accepted']==40
        r,w,spi,keys=await connect()
        first=encode_frame(encode_event(Event(0x202,kind=0x1a)),keys,spi=spi,sequence=1)
        w.write(first[:3]);await w.drain();await asyncio.sleep(.02)
        w.write(first[3:]);await w.drain()
        reply=decode_event(decode_frame(await read_wire(r),keys,expected_sequence=2).plaintext)
        assert reply.kind==0x1b
        assert struct.unpack('>iii',reply.payload)==(0,server.probe_port,0)
        # Native discovery must work before login progresses, without a retry
        # timer. Use a real UDP socket, then ensure it is released on shutdown.
        import socket
        from els_server.port_probe import probe_reply
        probe=b'\x15'+struct.pack('<QIH',1,0,0)
        udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        udp.setblocking(False);udp.bind(('127.0.0.1',0))
        try:
            loop=asyncio.get_running_loop()
            await loop.sock_sendto(udp,probe,('127.0.0.1',server.probe_port))
            response,source=await asyncio.wait_for(loop.sock_recvfrom(udp,128),.5)
            assert response==b'\x16'+socket.inet_aton('127.0.0.1')+struct.pack('<I',udp.getsockname()[1])
            assert source==('127.0.0.1',server.probe_port)
            for invalid in (b'',probe[:-1],b'\x16'+probe[1:],b'\x15'+struct.pack('<QIH',2,0,0),probe+b'\0'):
                assert probe_reply(invalid,udp.getsockname()) is None
            assert probe_reply(probe,('192.0.2.1',1234)) is None
        finally:udp.close()
        # Coalesced requests keep sequence/response ordering.
        wires=b''.join(encode_frame(encode_event(Event(0x202,kind=k)),keys,spi=spi,sequence=n)
                       for n,k in [(2,0x1e),(3,0x35)])
        w.write(wires);await w.drain()
        kinds=[decode_event(decode_frame(await read_wire(r),keys,expected_sequence=n).plaintext).kind for n in [3,4,5]]
        assert kinds==[0x1f,0x19c,0x36],kinds
        bad=encode_frame(encode_event(Event(0x202,kind=0x1ef)),keys,spi=spi,sequence=4)
        w.write(bad[:-1]+bytes([bad[-1]^1]));await w.drain()
        assert await asyncio.wait_for(r.read(),2)==b''
        await disconnect(w)
        # Bad length is rejected before allocation; partial frames expire.
        for packet in [struct.pack('<II',2**31,1),b'\x40']:
            r,w,_,_=await connect();w.write(packet);await w.drain()
            assert await asyncio.wait_for(r.read(),2)==b''
            await disconnect(w)
        r1,w1,_,_=await connect();r2,w2,_,_=await connect()
        r3,w3=await asyncio.open_connection(host,port);writers.append(w3)
        assert await asyncio.wait_for(r3.read(),2)==b''
        assert server.metrics['rejected']==1
        await server.close()
        assert server.probe_protocol.closed.done()
        assert await r1.read()==await r2.read()==b''
        await asyncio.sleep(0)
        assert not server.connections
        assert server.metrics['protocol_errors']==2
        assert any(e['event']=='connection_timeout' for e in events)
    finally:
        await server.close();app.close()
        for writer in writers:writer.close()
    # Listener release permits a clean restart on the same port.
    app=Application(config);server=GameServer(replace(config,port=port),app,log)
    try:await app.start();await server.start()
    finally:await server.close();app.close()
    return events


def main():
    with tempfile.TemporaryDirectory(prefix='server-runtime-',dir=ROOT/'analysis') as name:
        directory=Path(name)
        events=asyncio.run(run(directory))
        state=directory/'lease.sqlite3'
        with SaveLease(state):
            prepare_database(state)
            # A second PROCESS must be excluded, not only another object.
            code='from pathlib import Path; from els_server.storage.lifecycle import SaveLease;\nwith SaveLease(Path(__import__("sys").argv[1])): pass'
            other=subprocess.run([sys.executable,'-c',code,str(state)],cwd=ROOT,capture_output=True,text=True)
            assert other.returncode!=0 and 'already owned' in other.stderr
            db=sqlite3.connect(state)
            db.execute('CREATE TABLE sentinel(value INTEGER)');db.execute('INSERT INTO sentinel VALUES (123)');db.commit();db.close()
        with SaveLease(state):
            prepare_database(state);assert checkpoint_database(state)[0]==0
            db=sqlite3.connect(state);assert db.execute('SELECT value FROM sentinel').fetchone()==(123,);db.close()
        for kwargs in [dict(host='0.0.0.0'),dict(profile='retail'),dict(max_connections=0),dict(frame_timeout=float('nan')),dict(port=True)]:
            try:ServerConfig(**kwargs)
            except ValueError:pass
            else:raise AssertionError(kwargs)
        cfg=directory/'server.toml';cfg.write_text('[server]\nstate_file="save.sqlite3"\nlog_dir="logs"\n',encoding='utf8')
        assert ServerConfig.load(cfg).state_file==state.with_name('save.sqlite3')
        cfg.write_text('[server]\nunknown=true\n',encoding='utf8')
        try:ServerConfig.load(cfg)
        except ValueError:pass
        else:raise AssertionError('Unknown config accepted')
        config=ServerConfig(log_dir=directory/'logs',log_max_bytes=4096,log_backups=2)
        log=EventLog(config)
        # Silence stdout only for the volume/rotation check.
        for handler in log.logger.handlers[:]:
            if not hasattr(handler,'baseFilename'):log.logger.removeHandler(handler)
        for i in range(300):log('test_event',index=i,padding='x'*100)
        log.close()
        files=list(config.log_dir.glob('server.jsonl*'))
        assert len(files)==3 and sum(p.stat().st_size for p in files)<3*4096
        assert all(not any(k in e for k in ('payload_hex','plaintext_hex','test_session_keys')) for e in events)
        # Compatibility modules are aliases, preserving test instrumentation identity.
        import local_session
        import els_server.domain.local_session as implementation
        assert local_session is implementation
    print('PASS: TCP fragmentation/coalescing, 40 reconnects, MAC/length controls, timeouts, concurrent cap, shutdown/restart, save ownership/WAL, config validation and log rotation.')

if __name__=='__main__':main()
