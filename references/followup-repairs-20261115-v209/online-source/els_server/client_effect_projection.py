"""Small wire projections used only to compare actual client state with its input."""
import struct
import hashlib

EFFECT_MESSAGES=frozenset((0x115,0x2b,0xf0,0xf3,0xad8,0x105,0x21a))

def targets(kind,payload):
    if kind in (0xad8,0x105,0x21a):return inventory_targets(payload,4 if kind==0x21a else 0)
    if kind in (0x114,0x65f) and len(payload)>=24:
        uid,group,slot,template,metadata,count=struct.unpack_from('>QBhIBI',payload,4)
        return dict(item=dict(uid=str(uid),group=group,slot=slot,template=template,count=count))
    if kind==0x115 and len(payload)==22:
        uid,template=struct.unpack_from('>Qi',payload)
        return dict(effect_owner=str(uid),template=template,**effect_contract(template))
    if kind in (0xb7,0xba,0xbd) and payload:return dict(part=struct.unpack_from('>b',payload)[0])
    if kind==0x30c and len(payload)==4:return dict(trigger=struct.unpack('>i',payload)[0])
    if kind==0xf5 and len(payload)>=8:return dict(quest=struct.unpack_from('>i',payload,4)[0])
    if kind==0xf0 and len(payload)>=24:
        projected=targets(0xf3,struct.pack('>I',1)+payload)
        return projected
    if kind in (0x2b,0xf3):
        start=4 if kind==0x2b else 0
        if len(payload)<start+4:return {}
        count=struct.unpack_from('>I',payload,start)[0];position=start+4;quests=[];states=[]
        if count>256:return {}
        for _ in range(count):
            if position+24>len(payload):return {}
            qid,owner,unused,n=struct.unpack_from('>iQQI',payload,position)
            if n>64 or position+24+n*7>len(payload):return {}
            quests.append(qid)
            if len(states)<16:states.append(dict(quest=qid,owner=str(owner),objectives=[dict(zip(('id','count','completed'),v))for v in struct.iter_unpack('>iHB',payload[position+24:position+24+n*7])]))
            position+=24+n*7
        return dict(quests=quests[:16],quest_states=states,quests_omitted=max(0,len(quests)-16))
    return {}


def effect_contract(template):
    """Project pinned data; never invent mechanics for an unknown effect kind."""
    from els_server.domain.consumables import catalog
    try:entry=catalog().get(template)
    except (OSError,ValueError,KeyError):return dict(effect_coverage='catalog_unavailable')
    if entry is None:return dict(effect_coverage='catalog_missing')
    effects=[list(struct.unpack('<6I',bytes.fromhex(v)))for v in entry['effects']]
    return dict(effect_definition_sha256=hashlib.sha256(bytes.fromhex(entry['record_hex'])).hexdigest(),
                effect_vector=effects,effect_coverage='per_effect',linked_factor=struct.unpack_from('<I',bytes.fromhex(entry['record_hex']),0xa8)[0])


def inventory_targets(payload,start=0):
    # Reuse the existing D9A550 grammar, including options and expiry strings.
    from els_server.protocol.mail_attachment_messages import _Cursor
    cursor=_Cursor(payload);cursor.pos=start
    try:
        total=cursor.count(1024);items=[]
        for index in range(total):
            uid,group,slot=struct.unpack('>QBh',cursor.take(11))
            begin=cursor.pos
            cursor.item()
            template,metadata,count=struct.unpack_from('>IBI',payload,begin)
            cursor.take(9)
            if index<16:items.append(dict(uid=str(uid),group=group,slot=slot,template=template,count=count))
        return dict(items=items,items_omitted=max(0,total-16))
    except (ValueError,struct.error,UnicodeDecodeError):return dict(item_projection_unavailable=True)
