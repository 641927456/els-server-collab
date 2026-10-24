"""Original955 absolute CollectionData notification (10E9010)."""
from els_server.domain.el_search_collection import wire
from els_server.protocol.protocol_codec import Event

def notice(value):
    return Event(0x201,kind=0x955,payload=wire(value)+b'\x00')
