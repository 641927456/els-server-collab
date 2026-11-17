"""Exact A13/A14 sales-detail codec, native42D records in an ordered u8 map.

Values must come from the separately qualified actual-purchase provider. This
codec creates no item/UID/history or money. opaque_419 is not called a fee.
"""
from dataclasses import dataclass
import struct
from els_server.protocol.protocol_codec import Event
from els_server.domain.fashion_state import record
from els_server.domain.inventory_items import validate_item


def _integer(value, minimum, maximum, label):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(label)
    return value


@dataclass(frozen=True)
class Row:
    index: int
    source_id: int
    item: dict
    traded_price: int
    opaque_419: int
    quantity: int
    traded_at: int


def request(payload):
    if type(payload) is not bytes or payload != b'':
        raise ValueError('A13 requires an empty body')
    return None


def _row(row):
    if type(row) is not Row:
        raise ValueError('Exact sales-detail row required')
    _integer(row.index,0,29,'Native sales-detail index')
    _integer(row.source_id,1,2**64-1,'Actual source handle required')
    for value in (row.traded_price,row.opaque_419,row.traded_at):
        _integer(value,0,2**64-1,'Exact native u64 field required')
    _integer(row.quantity,1,2**31-1,'Positive native sold quantity required')
    item=validate_item(row.item)
    if item['count'] != row.quantity:
        raise ValueError('Sales detail must preserve actual sold quantity')
    # DB4F80 wrapper at native DTO+9, not a 44D listing or own-listing DTO.
    return (struct.pack('>BQ',row.index,row.source_id)+record(item)+
            struct.pack('>QQiQ',row.traded_price,row.opaque_419,row.quantity,row.traded_at))


def reply(rows=(), *, result=0):
    _integer(result,-2**31,2**31-1,'Native sales-detail result')
    if type(rows) not in (tuple,list) or len(rows)>30:
        raise ValueError('At most30 explicit native sales-detail rows')
    if result and rows:
        raise ValueError('Rejected sales detail has no successful rows')
    parts=tuple(_row(row)for row in rows)
    indices=tuple(row.index for row in rows)
    if indices != tuple(sorted(set(indices))):
        raise ValueError('Canonical unique ascending sales-detail indices required')
    payload=struct.pack('>iI',result,len(parts))+b''.join(parts)
    if len(payload)+64>1024*1024:
        raise ValueError('Native secure-frame response bound')
    return Event(0x201,kind=0xa14,payload=payload)
