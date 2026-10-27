"""Current-build random-item wire codecs; no spending authorization here."""
import struct
from dataclasses import dataclass
from els_server.protocol.protocol_codec import Event
from els_server.domain.inventory_items import inventory_payload,fixture,LOCAL_MAX_STACK

MAX_CHOICES=100
# DB7B20 reads a counted vector without the request-choice limit. A Lu/Ciel
# pool can exceed 100 after role-specific ordinary accessories are included.
MAX_PREVIEW_ENTRIES=256
# One consumed stack (or empty source slot), plus every reward instance.
# grant_items accepts at most LOCAL_MAX_STACK units in this draw's one plan.
MAX_RESULT_ITEMS=LOCAL_MAX_STACK+1


def _validate_result_vector(vector):
    """Frame the pinned D9A550 grammar, including variable item fields.

    A stack split changes several absolute rows. Neither their number nor
    their size is fixed: expiry strings, attributes and option lists vary.
    This validates framing only; owned assets are authorized by draw().
    The field grammar is also used by mail_attachment_messages._Cursor.item.
    """
    position=0
    def take(size):
        nonlocal position
        if size<0 or position+size>len(vector):
            raise ValueError('Invalid committed ice inventory vector')
        data=vector[position:position+size];position+=size;return data
    def count(maximum):
        value=int.from_bytes(take(4),'big')
        if value>maximum:raise ValueError('Invalid committed ice inventory vector')
        return value
    records=count(MAX_RESULT_ITEMS)
    if not records:raise ValueError('Invalid committed ice inventory vector')
    for _ in range(records):
        take(11)  # UID8, group1, slot2; zero UID clears an exhausted source.
        for field in fixture()['fields']:
            offset=int(field['offset'],0)
            if offset==0xd:take(4*count(4))
            elif offset==0x25:
                if count(33)!=33:raise ValueError('Invalid ice option array')
                for _ in range(33):take(4*count(64))
            elif offset==0x350:
                raw=take(count(256))
                if len(raw)%2:raise ValueError('Invalid ice expiry string')
                raw.decode('utf-16le')
            elif offset in (0x37d,0x389):
                if count(3)!=3:raise ValueError('Invalid ice fixed triple')
                take(12)
            elif offset in (0x33d,0x3ec):
                expected=bytes.fromhex(field['wire_hex'])
                if take(len(expected))!=expected:raise ValueError('Unsupported ice item state')
            else:take(len(bytes.fromhex(field['wire_hex'])))
        take(9)  # Inventory wrapper flag and auxiliary UID.
    if position!=len(vector):raise ValueError('Invalid committed ice inventory vector')

@dataclass(frozen=True)
class PreviewRequest:
    template:int
    keys:tuple[int,...]
    flag1:int
    flag2:int

@dataclass(frozen=True)
class UseRequest:
    uid:int
    flag1:int
    flag2:int
    flag3:int
    choices:tuple[int,...]
    option:int

def preview_request(payload):
    # 2353800: template, vector<int>, two bytes.
    if len(payload)<10:raise ValueError('Truncated random-item preview')
    template,n=struct.unpack_from('>iI',payload)
    if template<=0 or n>MAX_CHOICES or len(payload)!=10+4*n:raise ValueError('Invalid random-item preview')
    keys=struct.unpack_from('>'+str(n)+'i',payload,8)
    return PreviewRequest(template,keys,*payload[-2:])

def use_request(payload):
    # 2353C10 / DB1A20: UID,3bytes,ordered set<int>,i32 option.
    if len(payload)<19:raise ValueError('Truncated random-item use')
    uid,a,b,c,n=struct.unpack_from('>QBBBI',payload)
    if not 0<uid<2**63 or n>MAX_CHOICES or len(payload)!=19+4*n:raise ValueError('Invalid random-item use')
    choices=struct.unpack_from('>'+str(n)+'i',payload,15)
    if tuple(sorted(set(choices)))!=choices:raise ValueError('Noncanonical random-item choice set')
    option,=struct.unpack_from('>i',payload,15+4*n)
    return UseRequest(uid,a,b,c,choices,option)

def preview_ack(result,template,field=0,flag=0,selection_count=0,entries=(),tail=0):
    # 2271D30 / DB7B20: 12-byte entries, packed DTO fields.
    if len(entries)>MAX_PREVIEW_ENTRIES:raise ValueError('Too many random-item preview entries')
    data=struct.pack('>iiiBiI',result,template,field,flag,selection_count,len(entries))
    data+=b''.join(struct.pack('>iii',*row) for row in entries)+struct.pack('>B',tail)
    return Event(0x201,kind=0x55a,payload=data)

def result_ack(result,items,ed,*,field=0,experience=0,rewards=(),flags=(0,0,0),tail=0,removed=None):
    # 234B540: 3i32,map<int,int>,normal inventory vector,u64ED,3u8,i32.
    # The map is displayed reward data; 7E0110 copies it, not consumption.
    if len(rewards)>MAX_CHOICES or len({x[0] for x in rewards})!=len(rewards):raise ValueError('Invalid random-item reward map')
    if len(flags)!=3:raise ValueError('Invalid random-item result flags')
    data=struct.pack('>iiiI',result,field,experience,len(rewards))
    data+=b''.join(struct.pack('>ii',*row) for row in sorted(rewards))
    records=inventory_payload(items)
    if removed is not None:
        # 2239F10 removes the specified slot before inserting positive UIDs.
        # A zero-UID record therefore clears an exhausted consumable stack.
        from els_server.domain.inventory_items import validate_item,item_body,fixture
        original=validate_item(removed)
        from els_server.domain.inventory_items import native_ice_catalog
        if original['template'] not in {p['template'] for p in native_ice_catalog()['offers']} or original['count']!=1:raise ValueError('Invalid exhausted ice stack')
        # The grant may reuse the exhausted machine's slot. Native 2239F10
        # removes affected slots before inserting positive UIDs, so that slot
        # needs only its final reward record, as in ordinary cube updates.
        # Emit an empty record only when the consumed slot remains empty.
        if not any((x['group'],x['slot'])==(original['group'],original['slot']) for x in items):
            body=bytearray(item_body(original))
            for f in fixture()['fields']:
                if int(f['offset'],0) in (0,5):struct.pack_into('>i',body,f['wire_offset'],0)
            records=struct.pack('>I',len(items)+1)+records[4:]+struct.pack('>QBh',0,original['group'],original['slot'])+body+bytes(9)
    data+=records+struct.pack('>QBBBi',ed,*flags,tail)
    return Event(0x201,kind=0x197,payload=data)


def result_events(payload):
    """Apply committed inventory before the ice UI's presentation-only 197.

    Native 21FFE00 dispatches AD8 to 22704B0, which decodes a DD46E0
    vector and applies 2239F10 without an outstanding-request requirement.
    The original ice-button handler 2EB8D70 does not apply its 197 vector.
    Reuse the vector in the stored receipt so retries cannot generate a new
    reward or use a later, unrelated inventory snapshot.
    """
    if not isinstance(payload,bytes) or len(payload)<35:raise ValueError('Truncated stored ice result')
    if len(payload)>1024*1024-128:raise ValueError('Stored ice result exceeds frame budget')
    result,=struct.unpack_from('>i',payload)
    ack=Event(0x201,kind=0x197,payload=payload)
    if result!=0:return [ack]
    n,=struct.unpack_from('>I',payload,12)
    offset=16+8*n
    if n>MAX_CHOICES or offset+4+15>len(payload):raise ValueError('Invalid stored ice reward map')
    vector=payload[offset:-15]
    _validate_result_vector(vector)
    return [Event(0x201,kind=0xad8,payload=vector),ack]
