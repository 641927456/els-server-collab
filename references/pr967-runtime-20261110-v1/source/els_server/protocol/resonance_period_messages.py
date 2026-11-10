"""Pinned DC0A90 request and D36480/D3A080 ordinary period consumers."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.domain.fashion_state import move_ack

def request(payload):
 if type(payload)is not bytes or len(payload)!=13:raise ValueError('Original718 requires UID/stat/page')
 uid,stat,page=struct.unpack('>QiB',payload)
 if not 0<uid<2**63 or not 1<=page<=4:raise ValueError('Original718 scalar bounds')
 return uid,stat,page

def reply(changes=(),*,result=0):
 if type(result)is not int or result not in(0,256):raise ValueError('Original719 result')
 return Event(0x201,kind=0x719,payload=struct.pack('>i',result)+move_ack(changes)[:-4])

def notice(state):
 # Original71A also updates the manager's selected page; keep it nonzero even
 # for a cleared bonus. Full610 is used for cold restore and period expiry.
 if not 1<=state.selected_page<=4:raise ValueError('Original71A selected page')
 return Event(0x201,kind=0x71a,payload=struct.pack('>iiQB',state.field21,state.field25,state.field29,state.selected_page))
