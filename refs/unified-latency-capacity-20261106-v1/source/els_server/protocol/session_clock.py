"""DX11 1F0 wall date and numeric server clocks; other fields remain unset.

13966E0 reads a wide string, three int64 fields, uint32, two int64 fields.
The first int64 and uint32 become engine+4F0/+4F8; FE9B00 resets +530
to GetTickCount. FE4DF0 returns seconds + uint32(ms + elapsed_ticks)/1000.
The last two fields are not doubles (the former zero fixture hid this).
"""
import struct
import time
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import wstring
from datetime import datetime,timedelta,timezone


def session_clock_ack(*,unix_ms=None):
    if unix_ms is None:
        unix_ms=time.time_ns()//1_000_000
    if type(unix_ms) is not int or not 0<=unix_ms<2**63:
        raise ValueError('Invalid server clock milliseconds')
    seconds,milliseconds=divmod(unix_ms,1000)
    # 1396888 -> FE9B00 -> 374470 parses this local wall date into engine+4E8.
    # The same 1F0's numeric seconds still drive engine+4F0; do not replace the
    # client's title lifetime arithmetic with a server-generated countdown.
    display=datetime.fromtimestamp(seconds,timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    if len(display)!=19 or not 1970<=int(display[:4])<=2999:raise ValueError('Unsupported native session calendar')
    payload=wstring(display)+struct.pack('>QQQIQQ',seconds,0,0,milliseconds,0,0)
    return Event(0x201,kind=0x1f0,payload=payload)
