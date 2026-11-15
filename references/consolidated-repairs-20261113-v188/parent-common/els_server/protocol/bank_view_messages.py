"""Original 72E/72F other-character bank browsing, separate from owned slots."""
import struct
from els_server.domain.inventory_items import item_body
from els_server.protocol.local_messages import wstring
from els_server.storage.characters import validate_name


def request(payload):
    # 238FA5D -> C4DBD0/C5D040 -> 3B6D9A0 writes a UTF-16 byte length.
    if not isinstance(payload,bytes) or len(payload)<4:
        raise ValueError('Bank browser name size')
    size=struct.unpack_from('>I',payload)[0]
    if not 4<=size<=24 or size%2 or len(payload)!=size+4:
        raise ValueError('Bank browser name length')
    try:name=payload[4:].decode('utf-16le')
    except UnicodeDecodeError as exc:raise ValueError('Bank browser name encoding') from exc
    return validate_name(name)


def acknowledgement(uid=0,name='',capacity=0,entries=(),result=0):
    # 2394320: result:i32, selected character:u64, name:wstring, tier:i32,
    # map<UID,inventory row>. Group 14 is SORT_TYPE.ST_SHARE_BANK, a view cache.
    if result==0 and (type(uid) is not int or not 1001<=uid<2**63 or capacity not in (8,16,24,32,40,48)):
        raise ValueError('Invalid bank browser identity or tier')
    if result==0:validate_name(name)
    rows=[];uids=set();slots=set()
    for entry in entries:
        group,slot=entry['position'];item=entry['item']
        if group!=8 or not 0<=slot<capacity or item['uid'] in uids or slot in slots:
            raise ValueError('Invalid bank browser instance')
        uids.add(item['uid']);slots.add(slot)
        rows.append(struct.pack('>QQBh',item['uid'],item['uid'],14,slot)+item_body(item)+bytes(9))
    return struct.pack('>iQ',result,uid)+wstring(name)+struct.pack('>iI',capacity,len(rows))+b''.join(rows)
