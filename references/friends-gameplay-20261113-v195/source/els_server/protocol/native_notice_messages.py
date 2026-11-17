"""DX11 notification 0xDD, dispatched to the original Notice manager."""
import struct

from els_server.protocol.local_messages import wstring
from els_server.protocol.protocol_codec import Event


def notice(kind, text, *, dungeon=0, variant=1, source_item=0):
    return Event(0x201, kind=0xDD, payload=(
        struct.pack('>bb', kind, variant) + wstring(text)
        + struct.pack('>iIii', source_item, 0, dungeon, -1)))


def achievement(kind, *fields, dungeon=0, source_item=0):
    # The client splits names, IDs and levels on semicolons.
    return notice(kind, ';'.join(str(field).replace(';', '；') for field in fields),
                  dungeon=dungeon, source_item=source_item)
