"""Recorded native 9EF UID writer and 226B560 complete 9F0 consumer."""
import struct
from els_server.domain.fashion_state import record, empty_record
from els_server.protocol.protocol_codec import Event


def request(payload):
    if not isinstance(payload, bytes) or len(payload) != 8:
        raise ValueError('Tenebros identification request size')
    uid, = struct.unpack('>Q', payload)
    if not 0 < uid < 2**63:
        raise ValueError('Tenebros identification UID')
    return uid


def acknowledgement(changes=(), *, result=0):
    # The complete recorded consumer parses this Q but never uses it. It is
    # deliberately zero, without claiming an ED or target-UID interpretation.
    payload = struct.pack('>iQI', result, 0, len(changes)) + b''.join(
        empty_record(*point) if item is None else record(item)
        for point, item in changes)
    return Event(0x201, kind=0x9f0, payload=payload)
