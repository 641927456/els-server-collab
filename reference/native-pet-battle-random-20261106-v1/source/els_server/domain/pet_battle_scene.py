"""Original2B19880's two scene actors; they never supply combat or rewards.

NPC3265/3266 and flags come from the pinned original producer. Positions are
PetFightGameData Red/BlueTeamFinalDest + corresponding NpcOffstPositon.
The shared2CE decoder and2D0 encoder retain the existing native lifecycle.
"""
from functools import lru_cache
from copy import copy
import struct
from els_server.domain.dungeon_spawns import decode
from els_server.domain.dungeon_npcs import encode_npc
from els_server.protocol.protocol_codec import Event
from els_server.protocol.npc_uid_map import uid_translation_vector


# These invisible native collision receivers are not combatants. An omitted
# initialization map leaves native HP0 and suppresses the damage-state callback.
# Use the largest finite native float as collision capacity; no combat/reward
# writer reads it. The approved server-owned pet HP and damage remain separate.
COLLISION_CAPACITY=float.fromhex('0x1.fffffep+127')


@lru_cache(maxsize=2)
def initialization(template):
    from els_server.game_data import client_data
    from els_server.domain.dungeon_routes import route_catalog,npc_initialization
    source=client_data().npc(template)
    if source['enum']!='NPC_UNIT_ID.NUI_PETPVP_DUMMY_'+str(template-3264) or source['class_id']!=0 or not source['is_npc']:
        raise ValueError('Original pet collision actor definition')
    catalog=copy(route_catalog());catalog._data=dict(catalog._data)
    catalog._data['npcs']={str(template):dict(strings=['','',source['script'],'','',''])}
    return npc_initialization(catalog,template,COLLISION_CAPACITY)


@lru_cache(maxsize=2)
def descriptor(template):
    if template not in(3265,3266):raise ValueError('Outside pet scene actors')
    row=bytearray(0xa4)
    struct.pack_into('<iiBfff',row,0,-1,template,99,
                     250. if template==3265 else -250.,430.,250.)
    row[0x4d]=row[0x4e]=row[0x66]=row[0x79]=1
    struct.pack_into('<f',row,0x67,-1.)
    struct.pack_into('<Q',row,0x6d,2**64-1)
    struct.pack_into('<f',row,0x7c,-1.)
    if template==3266:
        row[0x4f]=row[0x65]=row[0x6b]=row[0x75]=1
    return bytes(row)


def spawn(payload):
    def validate(row,extra):
        template=struct.unpack_from('<i',row,4)[0]
        if extra or bytes(row)!=descriptor(template):
            raise ValueError('Pet scene original actor fields')
    rows=decode(payload,validate,parameters=True)
    if len(rows)!=2 or {struct.unpack_from('<i',r,4)[0]for r,e in rows}!={3265,3266}:
        raise ValueError('Pet scene original pair required')
    wire=[]
    for template in(3265,3266):
        row=bytearray(descriptor(template))
        struct.pack_into('<i',row,0,template-3265)
        wire.append(encode_npc(row,0))
    identifiers=uid_translation_vector(((0,3265),(1,3266)))
    initial=b''.join(struct.pack('>i',t-3265)+initialization(t)for t in(3265,3266))
    return Event(0x201,kind=0x2d0,payload=struct.pack('>I',2)+b''.join(wire)
        +bytes(8)+identifiers+struct.pack('>I',2)+initial+bytes(8))
