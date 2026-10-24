"""Current-build EE/EF/F0, F3, F4/F5 and native 2B quest restoration."""
import struct
from els_server.protocol.protocol_codec import Event

# Native 79B330 error text table, pinned DX11 client. Unlike -1, these
# results resolve to visible, applicable quest messages in 751120/F5.
QUEST_REQUIREMENTS_NOT_MET=187
QUEST_REWARD_UNAVAILABLE=2005
QUEST_REWARD_BAG_FULL=165

def request(kind,payload):
    if not isinstance(payload,bytes):raise ValueError('Quest request bytes')
    if kind==0xee:
        if len(payload)!=8:raise ValueError('Quest accept request size')
        quest,npc=struct.unpack('>ii',payload)
        return dict(quest=quest,npc=npc)
    if kind==0xfa:
        if len(payload)!=4:raise ValueError('Quest abandon request size')
        return dict(quest=struct.unpack('>i',payload)[0])
    if kind==0xf4:
        # 3046B60 -> 7B4C20 -> 7BF9B0 -> 7CFF80: quest, NPC,
        # map<int,int> selected rewards, five bools. 302F620 inserts
        # map[template]=template, obtained from STXItemSlot virtual +270.
        if len(payload)<17:raise ValueError('Quest reward request size')
        quest,npc,n=struct.unpack_from('>iiI',payload)
        if n>36 or len(payload)!=17+8*n:raise ValueError('Quest reward choice count')
        choices=[struct.unpack_from('>ii',payload,12+8*i) for i in range(n)]
        flags=payload[12+8*n:]
        if any(i not in (0,1) for i in flags):raise ValueError('Quest reward flags')
        if any(a<=0 or a!=b for a,b in choices) or len({a for a,b in choices})!=len(choices):raise ValueError('Quest reward choice identities')
        # 3046B60 ->7CFF80: flags[1] is Epic skip; flags[2:4] start as1.
        # Storage validates skip admission independently of this wire boolean.
        row=dict(quest=quest,npc=npc,flags=tuple(flags))
        if choices:row['choices']=tuple(choices)
        return row
    raise ValueError('Unsupported quest action')

def active_record(row):
    # DD6E80 DTO+4 -> DFC350 runtime+8 -> 3037260 selected-unit UID gate.
    # accepted_at remains persisted metadata, never this wire owner field.
    from els_server.storage.character_schema import character_uid
    from els_server.domain.seal_quests import quest_catalog,target
    objectives=row['objectives']
    limits={s['m_iID']:target(s) for s in quest_catalog().objectives(row['id'])}
    # D01840/D01640 consume the final byte as authoritative completion for
    # kill/clear objectives; count alone does not enable the reward button.
    return struct.pack('>iQQI',row['id'],character_uid(row['owner']),0,len(objectives))+b''.join(struct.pack('>iHB',s,n,int(n>=limits[s])) for s,n in sorted(objectives.items()))

def completed_record(row):return struct.pack('>iiQQ',row['id'],1,row['completed_at'],0)

def initialization(state):
    # DA3620 -> DB6070/DD6E80, DB60F0, C62740, DB7080, vector32.
    active=state['active'];done=state['completed']
    body=struct.pack('>iI',0,len(active))+b''.join(active_record(r) for r in active)
    body+=struct.pack('>I',len(done))+b''.join(completed_record(r) for r in done)+bytes(12)
    return Event(0x201,kind=0x2b,payload=body)

def accept_ack(result=0):return Event(0x201,kind=0xef,payload=struct.pack('>i',result))

def accepted(row):
    # 30318D0/F0 -> 3044B00: one active record, item vector, two ints.
    return Event(0x201,kind=0xf0,payload=active_record(row)+bytes(12))

def progress(rows):
    return Event(0x201,kind=0xf3,payload=struct.pack('>I',len(rows))+b''.join(active_record(r) for r in rows))

def reward_ack(quest,character,location,slots,balances,items,updates=(),*,consumed=(),result=0,replayed=False,completed_at=0):
    from els_server.protocol.local_messages import character_unit
    from els_server.domain.fashion_state import record,empty_record
    # 3047020 -> C5F7F0 consumes the same full-unit/inventory/map/bool
    # body as D9; the outer F5 adds a result, completed24, and two flags.
    delta={pos:item for pos,item in consumed}
    delta.update({(i['group'],i['slot']):i for i in updates})
    unit=character_unit(location,True,slots,balances,items,character)
    unit+=struct.pack('>I',len(delta))+b''.join(empty_record(*pos) if item is None else record(item) for pos,item in sorted(delta.items()))+bytes(5)
    body=struct.pack('>iiiQQ',result,quest,1,completed_at,0)+unit+bytes((0,int(replayed)))
    return Event(0x201,kind=0xf5,payload=body)
