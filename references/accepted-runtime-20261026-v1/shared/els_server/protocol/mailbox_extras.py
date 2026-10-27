"""Pinned DX11 blacklist, refresh and mailbox notification payloads.

20D/20E lists UID/name pairs without a result prefix. 210/212 carry
result/name/UID; 1CE carries map<byte,int>, an auxiliary vector, then bool.
Player 1CF serialization remains gated pending its protected writer proof.
"""
import struct
from els_server.protocol.local_messages import wstring


def empty_request(raw):
    if raw != b'':
        raise ValueError('Expected an empty mailbox request')


def name_request(raw):
    if not isinstance(raw, bytes) or len(raw) < 4:
        raise ValueError('Blacklist name size')
    length = struct.unpack_from('>I', raw)[0]
    if not 4 <= length <= 24 or length % 2 or len(raw) != 4 + length:
        raise ValueError('Blacklist name bound')
    name = raw[4:].decode('utf-16le')
    from els_server.storage.characters import validate_name
    return validate_name(name)


def uid_request(raw):
    if not isinstance(raw, bytes) or len(raw) != 8:
        raise ValueError('Blacklist UID size')
    uid = struct.unpack('>Q', raw)[0]
    if not 1001 <= uid < 2**63:
        raise ValueError('Blacklist UID bound')
    return uid


def blacklist_ack(rows=()):
    return struct.pack('>I', len(rows)) + b''.join(
        struct.pack('>Q', row['uid']) + wstring(row['name']) for row in rows)


def change_ack(row=None, result=0):
    row = row or {'name': '', 'uid': 0}
    return struct.pack('>i', result) + wstring(row['name']) + struct.pack('>Q', row['uid'])


def refresh_ack(result=0):
    return struct.pack('>i', result)


def notification(unread):
    # This candidate implements folder 0 only. Empty auxiliary vectors contain
    # no invented item data. Zero counts must clear the client's previous map.
    # 2DD7630 binds GetUnreadCount -> 2DD9270 (map at PostBox+40).
    # IsExistExtraSystemPost -> 2E176B0 reads PostBox+68, so the last
    # bool is false for these ordinary GM ED letters, even when unread.
    return struct.pack('>IBiIB', 1, 0, unread, 0, 0)


def send_failure(ed=0, result=-1):
    # Original 2DE4EB0: result, absolute balance, inventory vector, recipient.
    return struct.pack('>iQI', result, ed, 0) + wstring('')
