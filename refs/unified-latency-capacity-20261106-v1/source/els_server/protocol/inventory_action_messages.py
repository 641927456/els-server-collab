"""Pinned DX11 split (555/556) and discard (109/10A) UI messages.

2350C80 writes the five split fields; 2268940 reads vector/map/result.
2354A50 writes UID/count; 2278E50 reads result/reserved-Q/item record.
The reserved split map and discard scalar have no enabled local semantics.
"""
import struct
from els_server.domain.bag_capacity import BAG_GROUPS, wire_limit
from els_server.domain.fashion_state import empty_record, move_ack, record


def split_request(payload):
    if not isinstance(payload, bytes) or len(payload) != 14:
        raise ValueError('Split request length')
    sg, ss, dg, ds, quantity = struct.unpack('>BiBii', payload)
    if sg != dg or sg not in BAG_GROUPS or ss == ds or quantity <= 0:
        raise ValueError('Unsupported split positions or quantity')
    if not all(0 <= slot < wire_limit(sg) for slot in (ss, ds)):
        raise ValueError('Split slot bound')
    return (sg, ss), (dg, ds), quantity


def split_ack(changes=(), result=0):
    # 556: standard inventory vector, empty map<int,int>, signed result.
    return move_ack(changes)[:-4] + bytes(4) + struct.pack('>i', result)


def discard_request(payload):
    if not isinstance(payload, bytes) or len(payload) != 12:
        raise ValueError('Discard request length')
    uid, quantity = struct.unpack('>Qi', payload)
    if not 1 <= uid < 2**63 or quantity <= 0:
        raise ValueError('Discard identity/quantity bound')
    return uid, quantity


def discard_ack(item=None, position=(6, 0), result=0):
    return struct.pack('>iQ', result, 0) + (record(item) if item else empty_record(*position))
