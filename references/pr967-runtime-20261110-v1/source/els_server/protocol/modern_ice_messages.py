"""BD4/BD7/BD8/BD9/BDA/BDB layouts from the pinned native readers/writers."""
import struct
from els_server.protocol.protocol_codec import Event

def claim_request(payload):
    if len(payload)!=8:raise ValueError('Ice point selection size')
    machine,template=struct.unpack('>ii',payload)
    if machine<=0 or template<=0:raise ValueError('Ice point selection identity')
    return machine,template

def withdraw_request(payload):
    if len(payload)<4:raise ValueError('Ice bag withdrawal size')
    n,=struct.unpack_from('>I',payload)
    if n==0 or len(payload)!=4+12*n:raise ValueError('Ice bag withdrawal count')
    rows=tuple(struct.unpack_from('>Qi',payload,4+12*i)for i in range(n))
    if tuple(sorted(set(uid for uid,_ in rows)))!=tuple(uid for uid,_ in rows)or any(not 0<uid<2**63 or count<=0 for uid,count in rows):
        raise ValueError('Ice bag withdrawal entries')
    return rows

def bag(kind,items=(),code=0):
    return bag_changes(kind,tuple((i['slot'],i)for i in items),code)

def bag_changes(kind,changes=(),code=0):
    from els_server.domain.inventory_items import item_body
    from els_server.domain.fashion_state import empty_record
    # 197B030 / 197DAD0 address the dedicated native bag group 28.
    # Validate each item's ordinary body separately; only the wrapper denotes
    # its dedicated bag location. Slots are stable until native bag sorting.
    vector=struct.pack('>I',len(changes))+b''.join(
        empty_record(28,slot)if i is None else
        struct.pack('>QBh',i['uid'],28,slot)+item_body(dict(i,slot=0))+bytes(9)
        for slot,i in changes)
    return Event(0x201,kind=kind,payload=struct.pack('>i',code)+vector)

def bag_events(kind,items=()):
    return bag_change_events(kind,tuple((i['slot'],i)for i in items))

def bag_change_events(kind,changes=()):
    # Use the existing inventory publication's 80-record frame bound. Only the
    # first withdrawal packet acknowledges BD4; remaining rows are native BD5.
    if not changes:return [bag_changes(kind)]
    return [bag_changes(kind if n==0 else 0xbd5,changes[n:n+80])for n in range(0,len(changes),80)]

def point_rows(points):
    from els_server.domain.modern_ice import machines
    # DC79D0: map<i32, {i32 item,i32 shared-group,float percent}>.
    rows=[(m,m,r['point_group'],points/100.0)for m,r in machines().items()]
    return struct.pack('>I',len(rows))+b''.join(struct.pack('>iiif',*r)for r in sorted(rows))

def points(points,*,initial=False):return Event(0x201,kind=0xbd8 if initial else 0xbd9,payload=point_rows(points))
def claim(template,points,code=0):return Event(0x201,kind=0xbdb,payload=struct.pack('>ii',code,template)+point_rows(points))
