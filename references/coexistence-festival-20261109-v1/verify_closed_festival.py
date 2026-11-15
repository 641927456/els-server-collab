"""A previously saved festival visitor can reconnect and exit after closure."""
import asyncio
from contextlib import closing
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile

sys.path.insert(0, sys.argv[1])
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.domain.town_travel import catalog
from els_server.protocol.activity_2026_entries import CodeEntry, read
from els_server.protocol.protocol_codec import Event
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState


async def main():
    with tempfile.TemporaryDirectory(dir=Path(sys.argv[2]), prefix='closed-festival-') as temp:
        tmp = Path(temp)
        db_path = tmp / 'game.sqlite3'
        app = Application(ServerConfig(port=0, state_file=db_path, accounts_file=tmp / 'accounts.sqlite3',
            tls_cert=tmp / 'cert.pem', tls_key=tmp / 'key.pem', log_dir=tmp / 'logs'))
        session = None
        try:
            await app.start()
            account = app.registry.create('closedfestqa')
            identity = app.registry.authenticate(account['name'], account['token'])
            uid = Characters(db_path, account['id']).create('ClosedFest', 1, 'own-closed-festival')['uid']
            point = tuple(catalog()['towns']['1503']['xyz'])
            with closing(sqlite3.connect(db_path)) as db, db:
                db.execute('UPDATE characters SET level=10 WHERE uid=?', (uid,))
                db.execute('UPDATE reward_balances SET ed=300000 WHERE uid=?', (uid,))
                db.execute('UPDATE location SET town=1503,x=?,y=?,z=? WHERE uid=?', (*point, uid))
            assert LocalState(db_path, uid).load()['map'] == 1503
            session = await app.session(identity=identity)
            seq = 0

            async def send(kind, payload=b''):
                nonlocal seq
                seq += 1
                performers = (0,) if kind in (0x28, 0x225, 0x227, 0x58c) else ()
                return await app.call(session.handle, Event(0x202, kind=kind, payload=payload, performers=performers), seq)

            async def result(request, reply, payload):
                data, = [e.payload for e in await send(request, payload) if e.kind == reply]
                return data

            for kind in (0x1a, 0x1e, 0x35, 0x1ef, 0x39, 0x485, 0x490):
                await send(kind)
            entries, = [e.payload for e in await send(0x28, struct.pack('>Q', uid)) if e.kind == 0x4b9]
            assert read(entries)[107] == CodeEntry(False, 0, 0)
            for kind, payload in ((0x6e9, b''), (0x5bf, bytes(8)), (0x32, b'')):
                await send(kind, payload)
            assert (await result(0x225, 0x226, struct.pack('>iB', 1503, 0)))[:4] == bytes(4)
            assert (await result(0x227, 0x228, struct.pack('>fffBH', *point, 0, 0))) == bytes(4)
            assert session.phase == 'town_ready' and session.active_map == 1503
            assert (await result(0x911, 0x912, struct.pack('>i', 3)))[:4] != bytes(4)
            assert (await result(0x58c, 0x58d, struct.pack('>i3B', 20000, 0, 0, 0)))[:4] == bytes(4)
            assert (await result(0x225, 0x226, struct.pack('>iB', 20000, 1)))[:4] == bytes(4)
            exit_point = tuple(catalog()['towns']['20000']['xyz'])
            assert (await result(0x227, 0x228, struct.pack('>fffBH', *exit_point, 0, 0))) == bytes(4)
            assert LocalState(db_path, uid).load()['map'] == 20000
            assert (await result(0x58c, 0x58d, struct.pack('>i3B', 1503, 0, 0, 0)))[:4] != bytes(4)
            assert (await result(0x225, 0x226, struct.pack('>iB', 1503, 1)))[:4] != bytes(4)
            print('PASS: closed 107, stored 1503 loads, normal exit, no new entry or campfire grant')
        finally:
            if session is not None:
                await app.release(session)
            app.close()


asyncio.run(main())
