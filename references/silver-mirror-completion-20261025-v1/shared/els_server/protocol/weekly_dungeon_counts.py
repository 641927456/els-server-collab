"""Original861 full weekly map, currently only a qualified Mirror provider.

19 is the client's RDT_DEVILDOM6_TOWER, and 35860 is its shared pseudo-key.
Unknown27-byte fields keep compatibility values and are not named as clocks.
"""
import struct
from els_server.protocol.protocol_codec import Event

def notification(db,owner):
    from els_server.storage.silver_mirror_state import read
    state=read(db,owner)
    row=struct.pack('>iii?qi??',1,5-state['remaining'],5,False,0,19,False,False)
    if len(row)!=27:raise ValueError('Native weekly row extent')
    # No other current runtime writer supplies861. Future qualified providers
    # must be merged here: its original consumer replaces the entire map.
    return Event(0x201,kind=0x861,payload=struct.pack('>IiI',1,35860,1)+row)
