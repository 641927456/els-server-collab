"""Bounded tunnel authentication, sent only after the TLS peer is verified."""
import asyncio
import json
import struct

MAGIC=b'ELS-FRIENDS/1\n'
MAX_AUTH_BYTES=2048


async def read_json(reader):
    if await reader.readexactly(len(MAGIC))!=MAGIC:raise ValueError('Invalid friends tunnel protocol')
    size=struct.unpack('>H',await reader.readexactly(2))[0]
    if not 1<=size<=MAX_AUTH_BYTES:raise ValueError('Invalid friends authentication size')
    result=json.loads((await reader.readexactly(size)).decode('utf8'))
    if type(result) is not dict:raise ValueError('Invalid friends authentication document')
    return result


async def write_json(writer,document):
    body=json.dumps(document,separators=(',',':')).encode('utf8')
    if not 1<=len(body)<=MAX_AUTH_BYTES:raise ValueError('Friends authentication response too large')
    writer.write(MAGIC+struct.pack('>H',len(body))+body)
    await writer.drain()
