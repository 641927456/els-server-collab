"""Current44D query replies, distinct from A05's467-byte own-listing DTO.

Rows must come from the authoritative read_offers SQL snapshot. This module has
no fallback inventory, synthetic market, SQL writer or admission hook.
"""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import wstring
from els_server.domain.fashion_state import record
from els_server.domain.inventory_items import validate_item

REPLY_KINDS=frozenset((0xa01,0xa0b,0xa0d))

def _identity(value):
    if type(value) is not int or not 0<value<2**63:raise ValueError('Authoritative listing identity')
    return value

def simple_request(payload):
    if type(payload) is not bytes or payload!=b'\x01\x00':raise ValueError('Unqualified simple query request')
    return (1,False)

def listing(row):
    required={'listing_id','seller_char_uid','seller_account_id','seller_name','expires_at','unit_price','item'}
    if not isinstance(row,dict) or not required<=row.keys():raise ValueError('Incomplete authoritative offer snapshot')
    identity=_identity(row['listing_id']);seller=_identity(row['seller_char_uid']);_identity(row['seller_account_id'])
    if type(row['seller_name']) is not str or not row['seller_name'] or len(row['seller_name'].encode('utf-16le'))>4096:raise ValueError('Current seller character name')
    if type(row['expires_at']) is not int or not 0<row['expires_at']<2**63:raise ValueError('Absolute listing expiry')
    if type(row['unit_price']) is not int or not 0<row['unit_price']<=10_000_000_000:raise ValueError('Listing unit price')
    item=validate_item(row['item'])
    if item['count']<=0:raise ValueError('Positive remaining listing quantity')
    return (struct.pack('>QQ',identity,seller)+wstring(row['seller_name'])+
            struct.pack('>QQ',row['expires_at'],row['unit_price'])+record(item))

def query_reply(kind,rows=(),*,result=0,flag=False,text=''):
    if kind not in REPLY_KINDS:raise ValueError('Unqualified query reply kind')
    if type(result) is not int or not -2**31<=result<2**31 or type(flag) is not bool:raise ValueError('Query status')
    if not isinstance(rows,(tuple,list)) or type(text) is not str or len(text.encode('utf-16le'))>4096:raise ValueError('Query reply inputs')
    if result and(rows or flag):raise ValueError('Rejected query has no successful rows/flag')
    seen=set();parts=[]
    for row in rows:
        raw=listing(row)
        if row['listing_id'] in seen:raise ValueError('Duplicate listing identity')
        seen.add(row['listing_id']);parts.append(raw)
    payload=struct.pack('>iBI',result,int(flag),len(parts))+b''.join(parts)+wstring(text)
    if len(payload)+64>1024*1024:raise ValueError('Native secure-frame response bound')
    return Event(0x201,kind=kind,payload=payload)
