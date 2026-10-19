"""Pinned709 style preference; empty70A ACK and original UID+byte notice."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.storage.character_schema import character_uid

def style(value):
    if type(value) is not int or not 0<=value<=2:raise ValueError('LuCiel style must be0..2')
    return value

def request(payload):
    if not isinstance(payload,bytes) or len(payload)!=1:raise ValueError('LuCiel709 payload size')
    return style(payload[0])

def acknowledgement():
    # Whole23AE850/74FFA0 branch releases the70A waiter without a body.
    # No status, revision or current preference is invented in this ACK.
    return Event(0x201,kind=0x70a)

def notification(uid,value):
    # Whole2163CD0 accepts the exact UID+signed-byte form read at30D33A3.
    return Event(0x201,kind=0x70b,payload=struct.pack('>QB',character_uid(uid),style(value)))

def preference(character):
    value=style(character.get('luciel_style',0))
    if value and character.get('unit_type')!=10:raise ValueError('Foreign LuCiel preference')
    return value

def responses(uid,value):return [acknowledgement(),notification(uid,value)]


ACTIVE_REPLIES={0x4e2:0x4e3}

def active(value):
    if type(value) is not int or value not in (0,1):raise ValueError('LuCiel active unit must be0/1')
    return value

def active_request(payload):
    if not isinstance(payload,bytes) or len(payload)!=1:raise ValueError('LuCiel active payload size')
    return active(payload[0])

def active_notification(uid,value,kind=0x4e3):
    if type(kind) is not int or kind not in ACTIVE_REPLIES.values():raise ValueError('LuCiel active reply kind')
    return Event(0x201,kind=kind,payload=struct.pack('>QB',character_uid(uid),active(value)))

def active_preference(character):
    value=active(character.get('luciel_active_unit',0))
    if value and character.get('unit_type')!=10:raise ValueError('Foreign LuCiel active unit')
    return value

def active_response(kind,uid,value):
    if type(kind) is not int or kind not in ACTIVE_REPLIES:raise ValueError('Unsupported LuCiel active request')
    return active_notification(uid,value,ACTIVE_REPLIES[kind])
