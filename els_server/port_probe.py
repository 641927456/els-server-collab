"""Native loopback UDP endpoint discovery (DX11 1395F70 / 137BAA0)."""
import asyncio
import socket
import struct
import time


def probe_reply(data, address, account_ids=(1,)):
    # Native scatter/gather send: byte 15, uint64 account, uint32 IP,
    # uint16 local port, all host endian. Reply: byte 16 + two host uint32s.
    # Discovery stays on loopback; a TLS bridge supplies its authenticated IDs.
    host, port = address
    if (host != '127.0.0.1' or not 0 < port <= 65535 or len(data) != 15
            or data[0] != 0x15 or struct.unpack_from('<Q', data, 1)[0] not in account_ids):
        return None
    return b'\x16' + socket.inet_aton(host) + struct.pack('<I', port)


class PortProbe(asyncio.DatagramProtocol):
    def __init__(self, log, account_ids=(1,),on_discovery=None):
        self.log=log;self.transport=None;self.window=0.0;self.count=0
        self.account_ids=account_ids
        self.on_discovery=on_discovery
        self.closed=asyncio.get_running_loop().create_future()

    def connection_made(self, transport):
        self.transport=transport

    def datagram_received(self, data, address):
        reply=probe_reply(data,address,self.account_ids)
        if reply is None:return
        now=time.monotonic()
        if now-self.window>=1:self.window=now;self.count=0
        if self.count>=32:return
        self.count+=1
        if self.on_discovery:self.on_discovery(address)
        self.transport.sendto(reply,address)
        self.log('port_probe_replied',client_port=address[1])

    def error_received(self, error):
        self.log('port_probe_error',error=type(error).__name__)

    def connection_lost(self, error):
        if not self.closed.done():self.closed.set_result(None)
