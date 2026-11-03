"""Original DX11 244 -> 123A4E0 -> chat category6 / megaphone panel5."""
import struct
from els_server.protocol.local_messages import wstring, u32
from els_server.protocol.protocol_codec import Event


def announcement(sender, text):
    # Native reader: name, two i32s, bool, message, account Q, actor Q,
    # DB3650 attachment map. Server announcements have no player or item link.
    return Event(0x201, kind=0x244, payload=(
        wstring(sender) + struct.pack('>ii?', 0, 0, False) + wstring(text)
        + bytes(16) + u32(0)))
