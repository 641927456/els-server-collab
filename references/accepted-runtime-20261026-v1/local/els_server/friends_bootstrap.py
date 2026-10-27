"""Initial native relay handshake at the authenticated loopback bridge.

487660 sends an empty UID vector through 488190: tag 6, own character UID,
zero generation and tick. 485B80 case 7 consumes that 16-byte body and tick.
This only acknowledges the already connected relay and its current room.
Peer datagrams and subsequent generation/roster checks remain separate.
"""
import struct
import time
from els_server.port_probe import PortProbe


def initial_reply(data, address, bridge):
    relay=bridge.relay
    if (bridge.closing or relay is None or not relay.ready.is_set()
        or relay.failure or address!=bridge.game_address
        or address[0]!='127.0.0.1' or not 0<address[1]<=65535
        or len(data)!=17 or data[0]!=6):
        return None
    manifest=relay.manifest
    if manifest is None:return None
    uid,generation,_=struct.unpack('<QII',data[1:])
    if uid!=manifest['uid'] or generation!=0:return None
    return b'\x07'+data[1:]


class RelayBootstrapProbe(PortProbe):
    def __init__(self, bridge, discovery):
        super().__init__(bridge.log,bridge.account_ids,discovery)
        self.bridge=bridge

    def datagram_received(self, data, address):
        if data[:1]!=b'\x06':
            super().datagram_received(data,address)
            return
        reply=initial_reply(data,address,self.bridge)
        if reply is None:return
        now=time.monotonic()
        if now-self.window>=1:self.window=now;self.count=0
        if self.count>=32:return
        self.count+=1
        self.transport.sendto(reply,address)
        self.log('relay_bootstrap_replied',client_port=address[1],
                 uid=self.bridge.relay.manifest['uid'])
