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


