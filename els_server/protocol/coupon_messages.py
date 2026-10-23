"""Currentc881 ordinary GM coupon/cash-deposit wire, not retail billing.

Source: coupon-success-contract-v1/28a127. No package/service/option
selection support. Product/transaction IDs are stable local ledger identities.
"""
import struct
from els_server.protocol.protocol_codec import Event


def _i32(value):
    if type(value) is not int or not -(2**31)<=value<2**31:
        raise ValueError('Coupon signed integer bound')
    return struct.pack('>i',value)


def _wstring(value,limit=512):
    if not isinstance(value,str) or '\0' in value:
        raise ValueError('Coupon string shape')
    raw=value.encode('utf-16le')
    if len(raw)>limit:raise ValueError('Coupon string bound')
    return struct.pack('>I',len(raw))+raw


def redeem_request(payload):
    if not isinstance(payload,bytes) or len(payload)<10:
        raise ValueError('Coupon request shape')
    size=struct.unpack_from('>I',payload)[0]
    if not 2<=size<=40 or size%2 or len(payload)!=size+8 or payload[-4:]!=bytes(4):
        raise ValueError('Coupon request shape')
    try:text=payload[4:4+size].decode('utf-16le',errors='strict')
    except UnicodeError:raise ValueError('Coupon text shape') from None
    if '\0' in text:raise ValueError('Coupon text shape')
    return text


def redeem_ack(result=940):
    return Event(0x201,kind=0x1a1,payload=_i32(result))


def deposit_request(payload):
    if not isinstance(payload,bytes) or len(payload)!=8:
        raise ValueError('Coupon deposit request shape')
    capacity,page=struct.unpack('>ii',payload)
    if capacity!=21 or not 1<=page<=10000:
        raise ValueError('Coupon deposit page bound')
    return page


def deposit_ack(rows=(),result=0):
    if len(rows)>21:raise ValueError('Coupon deposit page bound')
    wire=[]
    for row in rows:
        trans,product=row['trans_no'],row['product_no']
        if (type(trans) is not int or not 1<=trans<2**31 or type(product) is not int
                or not 1<=product<2**31 or type(row['quantity']) is not int
                or not 1<=row['quantity']<=99):raise ValueError('Coupon order identity/count bound')
        # i64 transaction + order string + current ProductInfo. Neither
        # packed memory stride225 nor legacychar quantity is a wire format.
        part=struct.pack('>q',trans)+_wstring('GM-'+str(trans),64)
        part+=_i32(product)+_i32(row['template'])+_wstring(row['name'])
        part+=_i32(0)*2+bytes(1)+struct.pack('>H',row['quantity'])+bytes(2)
        part+=_wstring('')+bytes(1)  # unnamed constructor tailfalse
        part+=struct.pack('>I',0)+bytes([2])+_wstring('')*2+struct.pack('>q',0)+bytes(1)
        wire.append(part)
    return Event(0x201,kind=0xd7b,payload=_i32(result)+struct.pack('>I',len(wire))
                 +b''.join(wire)+bytes(12))


def withdrawal_request(payload):
    if not isinstance(payload,bytes) or len(payload)!=17 or payload[8:]!=bytes(9):
        raise ValueError('Coupon ordinary withdrawal shape')
    trans,product=struct.unpack_from('>ii',payload)
    if not 1<=trans<2**31 or not 1<=product<2**31:
        raise ValueError('Coupon order identity bound')
    return trans,product


def withdrawal_ack(items=(),result=-1,*,resurrection_count=0):
    from els_server.domain.inventory_items import inventory_payload
    from els_server.storage.resurrection_counter import validate_count
    # Capacity map is additive, never absolute and never replayed. Tail0
    # excludes the native special-service processing branch.
    return Event(0x201,kind=0xd7d,payload=_i32(result)+_i32(validate_count(resurrection_count))
                 +bytes(4)+inventory_payload(list(items))+_i32(0))
