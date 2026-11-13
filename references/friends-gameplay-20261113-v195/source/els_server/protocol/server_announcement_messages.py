"""Original DX11 244 -> 123A4E0 -> chat category6 / megaphone panel5."""
import struct
from els_server.protocol.local_messages import wstring
from els_server.protocol.protocol_codec import Event


def announcement(sender, text, *, channel=0, account=0, actor=0):
    # Native reader: name, two i32s, bool, message, account Q, actor Q,
    # DB3650 attachment map. A zero account/actor identifies server text.
    return Event(0x201, kind=0x244, payload=(
        wstring(sender) + struct.pack('>ii?', channel, 0, False) + wstring(text)
        + struct.pack('>QQI', account, actor, 0)))
