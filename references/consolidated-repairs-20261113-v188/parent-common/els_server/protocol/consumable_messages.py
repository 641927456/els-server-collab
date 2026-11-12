"""Current native 113/114/115 ordinary shortcut consumable protocol."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.domain.fashion_state import record,empty_record


def request(payload,*,automatic=False):
    # 30AF3B0 writes DTO slot:u16, byte3, byte2, byte4. Special modes
    # are deliberately rejected until their effects/entitlements are verified.
    if not isinstance(payload,bytes) or len(payload)!=5:raise ValueError('Consumable request length')
    slot,mode,party,special=struct.unpack('>HBBB',payload)
    if slot>=(2 if automatic else 6) or mode or party or special:raise ValueError('Unsupported consumable slot/mode')
    return slot


def acknowledgement(item=None,position=(6,0),template=-1,result=0,cooldown=-1.0,*,automatic=False,slot=0):
    body=record(item) if item is not None else empty_record(*position)
    return Event(0x201,kind=0x65f if automatic else 0x114,payload=struct.pack('>i',result)+body+struct.pack('>i?fH',template,False,cooldown,slot if automatic else 0))


def effect(owner,template):
    # Native 3055590 -> 1AB9D20 applies this actor's immutable item effects.
    return Event(0x201,kind=0x115,payload=struct.pack('>Qi?Q?',owner,template,False,0,False))
