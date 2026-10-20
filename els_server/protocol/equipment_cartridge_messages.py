"""Original Cartridge failure replies; successful operations remain unadmitted.

BF6600/BF70A0/BF7320/BF7C50 read the complete DTO before testing result
through 751120. Empty temporary maps/records/balances on failure are not state
snapshots. Never use these replies to acknowledge a successful operation.
"""
import struct
from els_server.protocol.protocol_codec import Event

REQUEST_ACKS = {0xd4e: 0xd4f, 0xd50: 0xd51, 0xd52: 0xd53, 0xd54: 0xd55}


def unavailable(kind):
    ack = REQUEST_ACKS[kind]
    # result, sentinel ID, empty collection, empty full-record vector.
    payload = struct.pack('>iiII', 2005, 0, 0, 0)
    if ack in (0xd4f, 0xd55):
        payload += bytes(8)  # Temporary points, consumed only on success.
    if ack == 0xd55:
        payload += bytes(8)  # Temporary ED, consumed only on success.
    return Event(0x201, kind=ack, payload=payload)
