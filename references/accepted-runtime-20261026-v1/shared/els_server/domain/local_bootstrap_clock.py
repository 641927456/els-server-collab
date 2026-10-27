"""Selected local DX11 resource clock from verified D92/D93 native paths.

Local envelope policy: the existing frontend ACK event0x101. Native session
delivery uses its configured receive event475 independently of that wire field.
Local clock policy: the selected runtime epoch expressed in UTC, offset0 seconds.
No retail server timezone/offset setting is asserted and no persistent state is
changed here. The selected factory must explicitly provide bootstrap_clock.
"""
from datetime import datetime,timezone
import struct
from els_server.protocol.protocol_codec import Event


def handle(session,event):
    if (event.event_id!=0x402 or event.kind!=0xd92 or
            session.client_build!='dx11_260923' or session.phase!='new' or
            session.role is not None):
        return None
    clock=getattr(session.activity2026_awards,'bootstrap_clock',None)
    if not callable(clock):
        return None
    if event.payload or event.payload_mode!=0:
        raise ValueError('Bootstrap clock request must have no payload')
    epoch=clock()
    if type(epoch) is not int or not 0<epoch<=4102444800:
        raise ValueError('Selected local bootstrap epoch out of range')
    text=datetime.fromtimestamp(epoch,timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    raw=text.encode('utf-16le')
    return [Event(0x101,kind=0xd93,payload=struct.pack('>I',len(raw))+raw+struct.pack('>Q',0))]
