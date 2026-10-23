"""Current native recruitment serializers; no client UI or timer replacement."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.social_messages import Reader,party_info,party_member
from els_server.protocol.local_messages import i32,u32,wstring


REQUESTS=frozenset((0x8ee,0x8f1,0x8f3,0x8f6,0x8f8,0x8fb,0x8fd,0x8ff,0x901))


def empty_request(payload):
    Reader(payload).end()


def target_request(payload):
    r=Reader(payload);uid=r.scalar('Q');r.end();return uid


def candidate_payload(payload):
    # 235D0D0 -> DA0420 echoes the complete PartyUserInfo previously sent
    # in 8F4/8F7. The domain MUST match all bytes to that canonical record;
    # no client-claimed UID, stats or optional fields become authority.
    Reader(payload)
    if len(payload)<185:raise ValueError('Recruitment candidate DTO truncated')
    return payload


def create_request(payload):
    # 35D6840 ->234CB40 ->235C6B0 ->2BDD530. Suffix ints are
    # native list filters, NOT guessed character level restrictions.
    r=Reader(payload);kind=r.scalar('B');dungeon=r.scalar('i')
    fields=tuple(r.scalar('B') for _ in range(6));title=r.text(80)
    region=r.scalar('i');listed=r.scalar('i')
    tail=tuple(r.scalar('B') for _ in range(3));last=r.scalar('i');r.end()
    return dict(kind=kind,dungeon=dungeon,fields=fields,title=title,
        region=region,listed=listed,tail=tail,last=last)


def edit_request(payload):
    # 2376BE0 ctor, then 35D6CC0 only replaces title and byte+0A.
    r=create_request(payload)
    if (r['kind']!=0 or r['dungeon']!=0 or r['fields']!=(255,0,0,0,255,1)
        or r['region']!=0 or r['listed']!=0 or r['tail']!=(0,0,0) or r['last']!=0):
        raise ValueError('Recruitment edit native defaults')
    return r


def info(party):
    r=party.get('recruitment')
    return party_info(party['id'],len(party['members']),party['dungeon'],
        name=r['title'] if r else 'Friends',recruitment=r)


def info_notice(party):return Event(0x201,kind=0x8f0,payload=info(party))


def row(party=None):
    # 2BE1AB0/35C96E0. The 0x62 native memory stride is NOT wire length.
    if party is None:return bytes(8)+wstring('')+wstring('')+bytes(26)
    r=party['recruitment'];host=party['leader'].account.character()['name']
    # Only the verified ordinary zero-flag path is admitted. These bytes
    # retain their native positions; no unproven flag names are assigned.
    if (tuple(r['flags'])!=(0,0) or not 1<=len(party['members'])<=r['maximum']<=4
        or r['maximum']<2 or r['listed']!=party['dungeon']):
        raise ValueError('Recruitment row source')
    return (struct.pack('>Q',party['id'])+wstring(r['title'])+wstring(host)
        +struct.pack('>iiiiBBq',len(party['members']),r['maximum'],r['region'],r['listed'],
            r['flags'][0],r['flags'][1],r['sort_key']))


def candidates(party,result=0,records=()):
    records=tuple(records)
    return Event(0x201,kind=0x8f7,payload=i32(result)+u32(len(records))+b''.join(records))


def ack(kind,result=0,party=None):
    body=i32(result)
    if kind==0x8f2:body+=info(party) if party else party_info(0,1)
    elif kind==0x900:body+=u32(len(party or ()))+b''.join(row(p) for p in party or ())
    elif kind==0x902:
        body+=row(party)
        members=party['members'] if party else ()
        body+=u32(len(members))+b''.join(struct.pack('>Q',s.account.uid)
            +party_member(party['id'],s,n,s is party['leader'],s in party['ready'])
            for n,s in enumerate(members))
    return Event(0x201,kind=kind,payload=body)


def answer_kind(kind):return {0x8ee:0x8ef,0x8f1:0x8f2,0x8f3:0x8f5,
    0x8f6:0x8f7,0x8f8:0x8f9,0x8fb:0x8fc,0x8fd:0x8fe,0x8ff:0x900,0x901:0x902}[kind]


def stopped():
    # 232A570 consumes exactly u8; zero is the quiet/default native branch.
    return Event(0x201,kind=0x8fa,payload=b'\0')
